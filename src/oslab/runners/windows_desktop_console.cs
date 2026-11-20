using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

// Desktop console for OSLab product commands (guest.screen.showCommands). OSLab uploads this file to the
// Windows guest and compiles it there with the .NET Framework C# compiler, so it must stay C# 5.
//
//   OslabConsole.exe start <attempt ID> <timeout seconds>
//     Runs as SYSTEM through QEMU Guest Agent. Starts the task registered for this command and
//     waits for its exit code, durations, window and byte counts. Output files stay until collection.
//   OslabConsole.exe read <attempt ID> <stdout|stderr> <offset> <length>
//     Reads one bounded binary chunk as Base64 over the guest agent's text channel.
//   OslabConsole.exe show <attempt ID>
//     Runs in the signed-in session. A guest job contains the command and any descendants,
//     so stopping this scheduled task also stops its product processes.
public static class OslabConsole
{
    // A completed console can stay visible after the caller has unregistered its task.
    const int LingerSeconds = 120;
    const int StartSeconds = 60;
    const int MaxChunkBytes = 12288;
    const int DisplayCharacters = 64000;
    const int ExtendedJobInformation = 9; // JobObjectExtendedLimitInformation
    const uint KillOnJobClose = 0x2000;
    static readonly Encoding StrictUtf8 = new UTF8Encoding(false, true);
    static readonly string Root = AppDomain.CurrentDomain.BaseDirectory;

    public static int Main(string[] args)
    {
        try
        {
            Guid attempt;
            if (args.Length >= 2 && Guid.TryParseExact(args[1], "N", out attempt))
            {
                string folder = Path.Combine(Root, "command-" + args[1]);
                switch (args[0])
                {
                    case "start":
                        if (args.Length == 3)
                        {
                            return Start(folder, args[1], int.Parse(args[2], CultureInfo.InvariantCulture));
                        }
                        break;
                    case "show":
                        if (args.Length == 2)
                        {
                            return Show(folder);
                        }
                        break;
                    case "read":
                        if (args.Length == 5)
                        {
                            long offset = long.Parse(args[3], CultureInfo.InvariantCulture);
                            int length = int.Parse(args[4], CultureInfo.InvariantCulture);
                            return ReadChunk(folder, args[2], offset, length);
                        }
                        break;
                }
            }
            Console.Error.WriteLine("Invalid desktop console arguments");
            return 2;
        }
        catch (Exception)
        {
            // Raw exceptions and product output can contain the command specification.
            Console.Error.WriteLine("The desktop console helper did not complete");
            return 1;
        }
    }

    static int Start(string folder, string attempt, int timeoutSeconds)
    {
        RunTool("schtasks.exe", "/Run /TN \"\\OSLab\\Console-" + attempt + "\"");

        Stopwatch clock = Stopwatch.StartNew();
        string donePath = Path.Combine(folder, "done.txt");
        string errorPath = Path.Combine(folder, "error.txt");
        string startedPath = Path.Combine(folder, "started.txt");
        string error = null;
        bool timedOut = false;
        while (!File.Exists(donePath))
        {
            if (File.Exists(errorPath))
            {
                error = File.ReadAllText(errorPath);
                break;
            }
            if (clock.Elapsed.TotalSeconds >= timeoutSeconds)
            {
                timedOut = true;
                break;
            }
            if (clock.Elapsed.TotalSeconds >= StartSeconds && !File.Exists(startedPath))
            {
                error = "The desktop console did not start. Is the desktop user signed in?";
                break;
            }
            Thread.Sleep(200);
        }

        string[] done = !timedOut && error == null
            ? File.ReadAllText(donePath).Trim().Split(' ')
            : null;
        StringBuilder json = new StringBuilder("{");
        json.Append("\"exitCode\":").Append(done == null ? "null" : done[0]);
        json.Append(",\"seconds\":").Append(done == null ? "null" : done[1]);
        json.Append(",\"timedOut\":").Append(timedOut ? "true" : "false");
        json.Append(",\"error\":").Append(error == null ? "null" : Quote(Encoding.UTF8.GetBytes(error)));
        json.Append(",\"window\":").Append(Quote(ReadBytes(Path.Combine(folder, "window.txt"))));
        json.Append(",\"font\":").Append(Quote(ReadBytes(Path.Combine(folder, "font.txt"))));
        json.Append(",\"codePage\":").Append(GetOEMCP().ToString(CultureInfo.InvariantCulture));
        json.Append(",\"stdoutBytes\":").Append(done == null ? 0 : new FileInfo(Path.Combine(folder, "stdout.bin")).Length);
        json.Append(",\"stderrBytes\":").Append(done == null ? 0 : new FileInfo(Path.Combine(folder, "stderr.bin")).Length);
        json.Append("}");
        Console.Out.WriteLine(json.ToString());
        return 0;
    }

    static int ReadChunk(string folder, string stream, long offset, int length)
    {
        if ((stream != "stdout" && stream != "stderr") || offset < 0 || length < 1 || length > MaxChunkBytes)
        {
            return 2;
        }
        byte[] buffer = new byte[length];
        using (FileStream file = File.OpenRead(Path.Combine(folder, stream + ".bin")))
        {
            file.Seek(offset, SeekOrigin.Begin);
            int used = 0;
            while (used < length)
            {
                int count = file.Read(buffer, used, length - used);
                if (count == 0)
                {
                    return 1;
                }
                used += count;
            }
        }
        Console.Out.WriteLine(Convert.ToBase64String(buffer));
        return 0;
    }

    static int Show(string folder)
    {
        try
        {
            WriteResult(folder, "started.txt", "");
            string specPath = Path.Combine(folder, "spec.txt");
            Dictionary<string, List<string>> spec = ReadSpec(specPath);
            File.Delete(specPath);
            IntPtr job = JoinCommandJob();
            Console.Title = spec["title"][0];
            // A UTF-8 window accepts Consolas and shows text in any language. Korean and Japanese code pages
            // only allow fonts that draw the backslash as a currency sign.
            Console.OutputEncoding = new UTF8Encoding(false);
            WriteResult(folder, "font.txt", SetFont(spec));
            WriteResult(folder, "window.txt", PlaceWindow(spec));

            WriteBanner(" OSLab  " + DateTime.Now.ToString("HH:mm:ss", CultureInfo.InvariantCulture) + " ", ConsoleColor.Cyan);
            Console.ForegroundColor = ConsoleColor.Cyan;
            Console.WriteLine(spec["prompt"][0] + " " + spec["display"][0]);
            Console.ResetColor();
            Console.WriteLine();

            ProcessStartInfo info = new ProcessStartInfo(spec["fileName"][0], spec["arguments"][0]);
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            info.RedirectStandardInput = true;
            info.RedirectStandardOutput = true;
            info.RedirectStandardError = true;
            info.WorkingDirectory = Environment.SystemDirectory;
            List<string> secrets = spec.ContainsKey("redact") ? spec["redact"] : new List<string>();
            Stopwatch clock = Stopwatch.StartNew();
            using (Process process = Process.Start(info))
            {
                process.StandardInput.Close();
                string stdout = Path.Combine(folder, "stdout.bin");
                string stderr = Path.Combine(folder, "stderr.bin");
                Task output = CopyStream(process.StandardOutput.BaseStream, stdout);
                Task errors = CopyStream(process.StandardError.BaseStream, stderr);
                Task.WaitAll(output, errors);
                process.WaitForExit();
                string seconds = clock.Elapsed.TotalSeconds.ToString("0.0", CultureInfo.InvariantCulture);
                Encoding codePage = Encoding.GetEncoding((int)GetOEMCP());
                ShowOutput(stdout, null, codePage, secrets);
                ShowOutput(stderr, ConsoleColor.Red, codePage, secrets);
                Console.WriteLine();
                WriteBanner(" exit code " + process.ExitCode + "  " + seconds + " s ", process.ExitCode == 0 ? ConsoleColor.Green : ConsoleColor.Red);
                CompleteCommandJob(job);
                WriteResult(folder, "done.txt", process.ExitCode.ToString(CultureInfo.InvariantCulture) + " " + seconds);
            }
            Thread.Sleep(LingerSeconds * 1000);
            return 0;
        }
        catch (Exception)
        {
            WriteResult(folder, "error.txt", "The interactive command did not complete");
            return 1;
        }
    }

    static Task CopyStream(Stream source, string path)
    {
        return Task.Factory.StartNew(() =>
        {
            using (FileStream file = File.Create(path))
            {
                source.CopyTo(file);
            }
        }, CancellationToken.None, TaskCreationOptions.LongRunning, TaskScheduler.Default);
    }

    // Show a bounded preview with enough lookahead to mask secrets across line and buffer boundaries.
    // The complete, original bytes remain in the stream file for assertions.
    static void ShowOutput(string path, ConsoleColor? color, Encoding codePage, List<string> secrets)
    {
        int lookahead = 0;
        foreach (string secret in secrets)
        {
            lookahead = Math.Max(lookahead, secret.Length - 1);
        }
        string text;
        try
        {
            text = ReadPreview(path, StrictUtf8, DisplayCharacters + lookahead);
        }
        catch (DecoderFallbackException)
        {
            text = ReadPreview(path, codePage, DisplayCharacters + lookahead);
        }

        foreach (string secret in secrets)
        {
            text = text.Replace(secret, "<redacted>");
        }
        if (color.HasValue)
        {
            Console.ForegroundColor = color.Value;
        }
        Console.Write(text.Substring(0, Math.Min(DisplayCharacters, text.Length)));
        Console.ResetColor();
    }

    static string ReadPreview(string path, Encoding encoding, int limit)
    {
        using (StreamReader reader = new StreamReader(path, encoding, false))
        {
            char[] buffer = new char[limit];
            int count = reader.ReadBlock(buffer, 0, limit);
            return new string(buffer, 0, count);
        }
    }

    // Assign this helper before it creates the product process. When the scheduler stops the helper,
    // Windows closes its non-inheritable job handle and terminates all remaining job members.
    static IntPtr JoinCommandJob()
    {
        IntPtr job = CreateJobObject(IntPtr.Zero, null);
        if (job == IntPtr.Zero)
        {
            throw new InvalidOperationException("Could not create the command job");
        }
        JobLimits limits = new JobLimits();
        limits.Basic.LimitFlags = KillOnJobClose;
        if (!SetInformationJobObject(job, ExtendedJobInformation, ref limits, (uint)Marshal.SizeOf(typeof(JobLimits))) ||
            !AssignProcessToJobObject(job, GetCurrentProcess()))
        {
            CloseHandle(job);
            throw new InvalidOperationException("Could not assign the desktop console to its command job");
        }
        return job;
    }

    // A normally completed command may intentionally leave a background product process running.
    static void CompleteCommandJob(IntPtr job)
    {
        JobLimits limits = new JobLimits();
        if (!SetInformationJobObject(job, ExtendedJobInformation, ref limits, (uint)Marshal.SizeOf(typeof(JobLimits))))
        {
            throw new InvalidOperationException("Could not complete the command job");
        }
        CloseHandle(job);
    }

    static void WriteBanner(string text, ConsoleColor background)
    {
        Console.ForegroundColor = ConsoleColor.Black;
        Console.BackgroundColor = background;
        Console.Write(text);
        Console.ResetColor();
        Console.WriteLine();
    }

    // Applies the first font in the spec that the console accepts and returns the font it uses.
    static string SetFont(Dictionary<string, List<string>> spec)
    {
        IntPtr output = GetStdHandle(-11);
        FontInfo applied = new FontInfo();
        foreach (string faceName in spec["fontName"])
        {
            FontInfo font = new FontInfo();
            font.Size = (uint)Marshal.SizeOf(typeof(FontInfo));
            font.Height = short.Parse(spec["fontSize"][0], CultureInfo.InvariantCulture);
            font.Family = 54;
            font.Weight = 400;
            font.FaceName = faceName;
            SetCurrentConsoleFontEx(output, false, ref font);
            applied.Size = (uint)Marshal.SizeOf(typeof(FontInfo));
            GetCurrentConsoleFontEx(output, false, ref applied);
            if (applied.FaceName == faceName)
            {
                break;
            }
        }
        return applied.FaceName + " " + applied.Height.ToString(CultureInfo.InvariantCulture);
    }

    // Moves the window to the requested rectangle and returns the rectangle Windows applied together with
    // the screen size: "left top width height screenWidth screenHeight".
    static string PlaceWindow(Dictionary<string, List<string>> spec)
    {
        IntPtr input = GetStdHandle(-10);
        uint mode;
        if (GetConsoleMode(input, out mode))
        {
            // Quick Edit would pause the command when someone clicks into the window.
            SetConsoleMode(input, (mode | 0x80) & ~0x40u);
        }
        int screenWidth = GetSystemMetrics(0);
        int screenHeight = GetSystemMetrics(1);
        int left = Number(spec, "left");
        int top = Number(spec, "top");
        int width = Math.Min(Number(spec, "width"), screenWidth - left);
        int height = Math.Min(Number(spec, "height"), screenHeight - top);
        IntPtr window = GetConsoleWindow();
        MoveWindow(window, left, top, width, height, true);
        try
        {
            // A buffer as wide as the window wraps long lines instead of adding a horizontal scroll bar.
            Console.SetBufferSize(Console.WindowWidth, 3000);
        }
        catch (Exception)
        {
        }
        MoveWindow(window, left, top, width, height, true);
        ShowWindow(window, 5);
        SetForegroundWindow(window);
        Rect rect;
        GetWindowRect(window, out rect);
        int[] values = { rect.Left, rect.Top, rect.Right - rect.Left, rect.Bottom - rect.Top, screenWidth, screenHeight };
        return string.Join(" ", values);
    }

    static int Number(Dictionary<string, List<string>> spec, string key)
    {
        return int.Parse(spec[key][0], CultureInfo.InvariantCulture);
    }

    // spec.txt holds one "key=base64(UTF-8 value)" pair per line; "redact" may repeat.
    static Dictionary<string, List<string>> ReadSpec(string path)
    {
        Dictionary<string, List<string>> spec = new Dictionary<string, List<string>>();
        foreach (string line in File.ReadAllLines(path, Encoding.ASCII))
        {
            int split = line.IndexOf('=');
            if (split <= 0)
            {
                continue;
            }
            string key = line.Substring(0, split);
            if (!spec.ContainsKey(key))
            {
                spec[key] = new List<string>();
            }
            spec[key].Add(Encoding.UTF8.GetString(Convert.FromBase64String(line.Substring(split + 1))));
        }
        return spec;
    }

    // Written under a temporary name first so that "start" never reads a half-written file.
    static void WriteResult(string folder, string fileName, string text)
    {
        string path = Path.Combine(folder, fileName);
        File.WriteAllText(path + ".tmp", text);
        File.Move(path + ".tmp", path);
    }

    static void RunTool(string fileName, string arguments)
    {
        ProcessStartInfo info = new ProcessStartInfo(fileName, arguments);
        info.UseShellExecute = false;
        info.CreateNoWindow = true;
        info.RedirectStandardOutput = true;
        info.RedirectStandardError = true;
        using (Process tool = Process.Start(info))
        {
            tool.BeginOutputReadLine();
            tool.BeginErrorReadLine();
            tool.WaitForExit();
            if (tool.ExitCode != 0)
            {
                throw new InvalidOperationException("Could not start the scheduled console command");
            }
        }
    }

    static byte[] ReadBytes(string path)
    {
        return File.Exists(path) ? File.ReadAllBytes(path) : new byte[0];
    }

    static string Quote(byte[] bytes)
    {
        return "\"" + Convert.ToBase64String(bytes) + "\"";
    }

    [StructLayout(LayoutKind.Sequential)]
    struct JobBasicLimits
    {
        public long ProcessUserTimeLimit;
        public long JobUserTimeLimit;
        public uint LimitFlags;
        public UIntPtr MinimumWorkingSetSize;
        public UIntPtr MaximumWorkingSetSize;
        public uint ActiveProcessLimit;
        public UIntPtr Affinity;
        public uint PriorityClass;
        public uint SchedulingClass;
    }

    [StructLayout(LayoutKind.Sequential)]
    struct IoCounters
    {
        public ulong ReadOperations;
        public ulong WriteOperations;
        public ulong OtherOperations;
        public ulong ReadBytes;
        public ulong WriteBytes;
        public ulong OtherBytes;
    }

    [StructLayout(LayoutKind.Sequential)]
    struct JobLimits
    {
        public JobBasicLimits Basic;
        public IoCounters Io;
        public UIntPtr ProcessMemoryLimit;
        public UIntPtr JobMemoryLimit;
        public UIntPtr PeakProcessMemoryUsed;
        public UIntPtr PeakJobMemoryUsed;
    }

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    static extern IntPtr CreateJobObject(IntPtr attributes, string name);

    [DllImport("kernel32.dll")]
    static extern bool SetInformationJobObject(IntPtr job, int infoClass, ref JobLimits info, uint infoLength);

    [DllImport("kernel32.dll")]
    static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);

    [DllImport("kernel32.dll")]
    static extern IntPtr GetCurrentProcess();

    [DllImport("kernel32.dll")]
    static extern bool CloseHandle(IntPtr handle);

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    struct FontInfo
    {
        public uint Size;
        public uint Index;
        public short Width;
        public short Height;
        public int Family;
        public int Weight;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
        public string FaceName;
    }

    [StructLayout(LayoutKind.Sequential)]
    struct Rect
    {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

    [DllImport("kernel32.dll")]
    static extern IntPtr GetConsoleWindow();

    [DllImport("kernel32.dll")]
    static extern IntPtr GetStdHandle(int handle);

    [DllImport("kernel32.dll")]
    static extern bool GetConsoleMode(IntPtr handle, out uint mode);

    [DllImport("kernel32.dll")]
    static extern bool SetConsoleMode(IntPtr handle, uint mode);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    static extern bool SetCurrentConsoleFontEx(IntPtr output, bool maximumWindow, ref FontInfo font);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    static extern bool GetCurrentConsoleFontEx(IntPtr output, bool maximumWindow, ref FontInfo font);

    [DllImport("kernel32.dll")]
    static extern uint GetOEMCP();

    [DllImport("user32.dll")]
    static extern bool MoveWindow(IntPtr window, int left, int top, int width, int height, bool repaint);

    [DllImport("user32.dll")]
    static extern bool GetWindowRect(IntPtr window, out Rect rect);

    [DllImport("user32.dll")]
    static extern bool ShowWindow(IntPtr window, int command);

    [DllImport("user32.dll")]
    static extern bool SetForegroundWindow(IntPtr window);

    [DllImport("user32.dll")]
    static extern int GetSystemMetrics(int index);
}
