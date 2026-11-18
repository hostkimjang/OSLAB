[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$DataDir,
    [string]$Version = '1.0',
    [switch]$Regression
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName PresentationFramework, Microsoft.VisualBasic

$dataPath = [IO.Path]::GetFullPath($DataDir)
$null = New-Item -ItemType Directory -Path $dataPath -Force
$inputPath = Join-Path $dataPath 'input.csv'
$statePath = Join-Path $dataPath 'dispatch-state.json'
$exportPath = Join-Path $dataPath 'dispatch-export.csv'
$inputColumns = @('Id', 'Customer', 'Destination', 'Units', 'Priority')
$exportColumns = $inputColumns + 'Status'
$utf8 = [Text.UTF8Encoding]::new($false)

$state = [ordered]@{
    Version = $Version
    Records = @()
    Rejected = @()
    Events = @()
    LastExport = $null
}
if ([IO.File]::Exists($statePath)) {
    $saved = [IO.File]::ReadAllText($statePath) | ConvertFrom-Json
    $state.Records = @($saved.Records)
    $state.Rejected = @($saved.Rejected)
    $state.Events = @($saved.Events)
    $state.LastExport = $saved.LastExport
}

function Save-DispatchState {
    $payload = ConvertTo-Json -InputObject $state -Depth 8
    $pending = "$statePath.pending"
    [IO.File]::WriteAllText($pending, $payload, $utf8)
    if ([IO.File]::Exists($statePath)) {
        [IO.File]::Replace($pending, $statePath, [NullString]::Value)
    } else {
        [IO.File]::Move($pending, $statePath)
    }
}

function Add-DispatchEvent([string]$Action, [string]$Details) {
    $state.Events += [pscustomobject][ordered]@{
        Action = $Action
        Version = $Version
        Details = $Details
        At = [DateTimeOffset]::UtcNow.ToString('o')
    }
    Save-DispatchState
}

function Read-DispatchInput {
    $records = [Collections.Generic.List[object]]::new()
    $rejected = [Collections.Generic.List[object]]::new()
    $ids = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    $parser = [Microsoft.VisualBasic.FileIO.TextFieldParser]::new($inputPath, $utf8)
    $parser.SetDelimiters(',')
    $parser.HasFieldsEnclosedInQuotes = $true
    try {
        $header = $parser.ReadFields()
        if (($header -join ',') -cne ($inputColumns -join ',')) {
            throw 'Input CSV must contain Id, Customer, Destination, Units and Priority in that order.'
        }
        while (!$parser.EndOfData) {
            $lineNumber = $parser.LineNumber
            try {
                $fields = $parser.ReadFields()
            } catch [Microsoft.VisualBasic.FileIO.MalformedLineException] {
                $rejected.Add([pscustomobject]@{ Id = "Line $lineNumber"; Reason = 'Invalid CSV quoting' })
                continue
            }
            $id = $fields[0]
            $units = 0
            $reason = if ($fields.Count -ne $inputColumns.Count) {
                'Incorrect column count'
            } elseif ([string]::IsNullOrWhiteSpace($id) -or [string]::IsNullOrWhiteSpace($fields[1]) -or
                [string]::IsNullOrWhiteSpace($fields[2])) {
                'Shipment, customer and destination are required'
            } elseif (![int]::TryParse($fields[3], [Globalization.NumberStyles]::None,
                    [Globalization.CultureInfo]::InvariantCulture, [ref]$units) -or $units -le 0) {
                'Units must be a positive whole number'
            } elseif ($fields[4] -cnotin @('Standard', 'Express')) {
                'Priority must be Standard or Express'
            } elseif (!$ids.Add($id)) {
                'Duplicate shipment'
            }
            if ($reason) {
                $rejected.Add([pscustomobject]@{ Id = $id; Reason = $reason })
                continue
            }
            $records.Add([pscustomobject][ordered]@{
                Id = $id
                Customer = $fields[1]
                Destination = $fields[2]
                Units = $units
                Priority = $fields[4]
                Status = 'Ready'
            })
        }
    } finally {
        $parser.Dispose()
    }
    [pscustomobject]@{ Records = $records.ToArray(); Rejected = $rejected.ToArray() }
}

$xaml = @'
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Dispatch Board" WindowState="Maximized" WindowStartupLocation="CenterScreen"
        Width="1240" Height="760" MinWidth="970" MinHeight="610"
        Background="#F0F3F8" FontFamily="Segoe UI" FontSize="14" UseLayoutRounding="True">
    <Window.Resources>
        <Style TargetType="Button">
            <Setter Property="Padding" Value="17,8"/>
            <Setter Property="Height" Value="34"/>
            <Setter Property="Cursor" Value="Hand"/>
            <Setter Property="Foreground" Value="#1D3555"/>
            <Setter Property="Background" Value="#F5F7FB"/>
            <Setter Property="BorderBrush" Value="#D7E0ED"/>
            <Setter Property="BorderThickness" Value="1"/>
            <Setter Property="FontWeight" Value="SemiBold"/>
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="Button">
                        <Border x:Name="ButtonSurface" Background="{TemplateBinding Background}"
                                BorderBrush="{TemplateBinding BorderBrush}" BorderThickness="{TemplateBinding BorderThickness}"
                                CornerRadius="6" Padding="{TemplateBinding Padding}">
                            <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
                        </Border>
                        <ControlTemplate.Triggers>
                            <Trigger Property="IsMouseOver" Value="True">
                                <Setter TargetName="ButtonSurface" Property="Opacity" Value="0.83"/>
                            </Trigger>
                            <Trigger Property="IsKeyboardFocused" Value="True">
                                <Setter TargetName="ButtonSurface" Property="BorderBrush" Value="#5E91F4"/>
                            </Trigger>
                            <Trigger Property="IsEnabled" Value="False">
                                <Setter TargetName="ButtonSurface" Property="Opacity" Value="0.46"/>
                            </Trigger>
                        </ControlTemplate.Triggers>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
        </Style>
        <Style x:Key="MetricCard" TargetType="Border">
            <Setter Property="Background" Value="White"/>
            <Setter Property="BorderBrush" Value="#DDE5EF"/>
            <Setter Property="BorderThickness" Value="1"/>
            <Setter Property="CornerRadius" Value="9"/>
            <Setter Property="Padding" Value="17,11"/>
        </Style>
        <Style x:Key="MetricHeading" TargetType="TextBlock">
            <Setter Property="FontSize" Value="12"/>
            <Setter Property="FontWeight" Value="SemiBold"/>
            <Setter Property="Foreground" Value="#536981"/>
        </Style>
        <Style x:Key="MetricValue" TargetType="TextBlock">
            <Setter Property="FontSize" Value="25"/>
            <Setter Property="FontWeight" Value="Bold"/>
            <Setter Property="Margin" Value="0,1,0,2"/>
        </Style>
        <Style TargetType="DataGridColumnHeader">
            <Setter Property="Background" Value="#EAF0F8"/>
            <Setter Property="Padding" Value="11,9"/>
            <Setter Property="Foreground" Value="#405A78"/>
            <Setter Property="FontWeight" Value="SemiBold"/>
            <Setter Property="BorderThickness" Value="0"/>
        </Style>
        <Style TargetType="DataGridCell">
            <Setter Property="Padding" Value="10,4"/>
            <Setter Property="BorderThickness" Value="0"/>
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="DataGridCell">
                        <Border Padding="{TemplateBinding Padding}" Background="{TemplateBinding Background}">
                            <ContentPresenter VerticalAlignment="Center"/>
                        </Border>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
        </Style>
        <Style TargetType="DataGridRow">
            <Setter Property="Foreground" Value="#213C58"/>
            <Style.Triggers>
                <DataTrigger Binding="{Binding Status}" Value="On Hold">
                    <Setter Property="Foreground" Value="#964220"/>
                    <Setter Property="FontWeight" Value="SemiBold"/>
                </DataTrigger>
                <Trigger Property="IsSelected" Value="True">
                    <Setter Property="Background" Value="#D5E4FF"/>
                    <Setter Property="Foreground" Value="#193D78"/>
                </Trigger>
            </Style.Triggers>
        </Style>
    </Window.Resources>
    <Grid Margin="24,18,24,16">
        <Grid.RowDefinitions>
            <RowDefinition Height="126"/>
            <RowDefinition Height="103"/>
            <RowDefinition Height="*"/>
            <RowDefinition Height="38"/>
        </Grid.RowDefinitions>
        <Border Grid.Row="0" CornerRadius="12" Padding="23,14">
            <Border.Background>
                <LinearGradientBrush StartPoint="0,0" EndPoint="1,1">
                    <GradientStop Color="#0B1D36" Offset="0"/>
                    <GradientStop Color="#163F70" Offset="0.73"/>
                    <GradientStop Color="#155E74" Offset="1"/>
                </LinearGradientBrush>
            </Border.Background>
            <Grid>
                <StackPanel VerticalAlignment="Center">
                    <TextBlock Text="FULFILLMENT OPERATIONS" Foreground="#8FE0DB" FontSize="12" FontWeight="SemiBold"/>
                    <TextBlock Text="Dispatch Board" Foreground="White" FontSize="36" FontWeight="Bold" Margin="0,2,0,1"/>
                    <TextBlock Text="Validate incoming shipments, resolve holds and release a dispatch manifest." Foreground="#C8D8EC" FontSize="14"/>
                </StackPanel>
                <Border HorizontalAlignment="Right" VerticalAlignment="Top" Margin="0,3,0,0" Background="#204E72"
                        BorderBrush="#4B7D9E" BorderThickness="1" CornerRadius="12" Padding="11,5">
                    <TextBlock x:Name="ReleaseBadge" Foreground="#E4F5FF" FontSize="12" FontWeight="SemiBold"/>
                </Border>
                <StackPanel Orientation="Horizontal" HorizontalAlignment="Right" VerticalAlignment="Bottom" Margin="0,0,1,2">
                    <Border Background="#3577A2" CornerRadius="2" Width="21" Height="4" Margin="0,0,5,0"/>
                    <Border Background="#49A5BC" CornerRadius="2" Width="34" Height="4" Margin="0,0,5,0"/>
                    <Border Background="#79DCD4" CornerRadius="2" Width="51" Height="4"/>
                </StackPanel>
            </Grid>
        </Border>
        <Grid Grid.Row="1" Margin="0,13,0,12">
            <Grid.ColumnDefinitions>
                <ColumnDefinition Width="*"/>
                <ColumnDefinition Width="12"/>
                <ColumnDefinition Width="*"/>
                <ColumnDefinition Width="12"/>
                <ColumnDefinition Width="*"/>
            </Grid.ColumnDefinitions>
            <Border Style="{StaticResource MetricCard}">
                <StackPanel>
                    <TextBlock Text="VALIDATED SHIPMENTS" Style="{StaticResource MetricHeading}"/>
                    <TextBlock x:Name="AcceptedMetric" Style="{StaticResource MetricValue}" Foreground="#12695F"/>
                </StackPanel>
            </Border>
            <Border Grid.Column="2" Style="{StaticResource MetricCard}">
                <StackPanel>
                    <TextBlock Text="REJECTED ROWS" Style="{StaticResource MetricHeading}"/>
                    <TextBlock x:Name="RejectedMetric" Style="{StaticResource MetricValue}" Foreground="#AA571E"/>
                </StackPanel>
            </Border>
            <Border Grid.Column="4" Style="{StaticResource MetricCard}">
                <StackPanel>
                    <TextBlock Text="SHIPMENTS ON HOLD" Style="{StaticResource MetricHeading}"/>
                    <TextBlock x:Name="HeldMetric" Style="{StaticResource MetricValue}" Foreground="#2852A0"/>
                </StackPanel>
            </Border>
        </Grid>
        <Grid Grid.Row="2">
            <Grid.ColumnDefinitions>
                <ColumnDefinition Width="*"/>
                <ColumnDefinition Width="12"/>
                <ColumnDefinition Width="285"/>
            </Grid.ColumnDefinitions>
            <Border Style="{StaticResource MetricCard}" Padding="15,13,15,15">
                <Grid>
                    <Grid.RowDefinitions>
                        <RowDefinition Height="34"/>
                        <RowDefinition Height="46"/>
                        <RowDefinition Height="*"/>
                    </Grid.RowDefinitions>
                    <TextBlock Text="Shipment queue" FontSize="21" FontWeight="Bold" Foreground="#163553"/>
                    <Grid Grid.Row="1" Margin="0,0,0,10">
                        <StackPanel Orientation="Horizontal" HorizontalAlignment="Left" VerticalAlignment="Center">
                            <Button x:Name="ImportButton" Content="Import CSV" Background="#165DD6" Foreground="White"
                                    BorderBrush="#165DD6" ToolTip="Ctrl+I"/>
                            <Button x:Name="HoldButton" Content="Hold / release" Margin="8,0,0,0" ToolTip="Ctrl+H"/>
                            <Button x:Name="ExportButton" Content="Export manifest" Margin="8,0,0,0" ToolTip="Ctrl+E"/>
                        </StackPanel>
                        <StackPanel Orientation="Horizontal" HorizontalAlignment="Right" VerticalAlignment="Center">
                            <TextBlock Text="Search" VerticalAlignment="Center" Foreground="#536981" Margin="0,0,9,0"/>
                            <TextBox x:Name="SearchBox" Width="125" Height="34" BorderBrush="#D7E0ED" Padding="7,4"
                                     VerticalContentAlignment="Center" ToolTip="Ctrl+F"/>
                        </StackPanel>
                    </Grid>
                    <Border Grid.Row="2" BorderBrush="#DDE5EF" BorderThickness="1" CornerRadius="6" ClipToBounds="True">
                        <Grid>
                            <DataGrid x:Name="QueueGrid" AutoGenerateColumns="False" IsReadOnly="True" HeadersVisibility="Column"
                                      GridLinesVisibility="Horizontal" HorizontalGridLinesBrush="#E6EDF5" BorderThickness="0"
                                      AlternatingRowBackground="#F6F9FD" RowHeight="35" Background="White"
                                      SelectionMode="Single" SelectionUnit="FullRow" CanUserAddRows="False">
                                <DataGrid.Columns>
                                    <DataGridTextColumn Header="Shipment" Binding="{Binding Id}" Width="97"/>
                                    <DataGridTextColumn Header="Customer" Binding="{Binding Customer}" Width="1.4*"/>
                                    <DataGridTextColumn Header="Destination" Binding="{Binding Destination}" Width="1.15*"/>
                                    <DataGridTextColumn Header="Units" Binding="{Binding Units}" Width="62"/>
                                    <DataGridTextColumn Header="Priority" Binding="{Binding Priority}" Width="90"/>
                                    <DataGridTextColumn Header="Status" Binding="{Binding Status}" Width="86"/>
                                </DataGrid.Columns>
                            </DataGrid>
                            <StackPanel x:Name="EmptyQueue" VerticalAlignment="Center" HorizontalAlignment="Center" IsHitTestVisible="False"
                                        Margin="0,24,0,0">
                                <TextBlock x:Name="EmptyTitle" TextAlignment="Center" Foreground="#284765" FontSize="20" FontWeight="SemiBold"/>
                                <TextBlock x:Name="EmptyDetail" TextAlignment="Center" Foreground="#5D758F" Margin="0,5,0,0"/>
                            </StackPanel>
                        </Grid>
                    </Border>
                </Grid>
            </Border>
            <Border Grid.Column="2" Style="{StaticResource MetricCard}" Padding="17,13">
                <Grid>
                    <Grid.RowDefinitions>
                        <RowDefinition Height="Auto"/>
                        <RowDefinition Height="Auto"/>
                        <RowDefinition Height="154"/>
                        <RowDefinition Height="Auto"/>
                        <RowDefinition Height="*"/>
                    </Grid.RowDefinitions>
                    <TextBlock Text="Run activity" FontSize="21" FontWeight="Bold" Foreground="#163553"/>
                    <Border Grid.Row="1" Background="#FFF3E4" CornerRadius="6" Padding="10" Margin="0,10,0,8">
                        <TextBlock x:Name="Validation" Foreground="#8D4A1B" TextWrapping="Wrap" FontSize="12"/>
                    </Border>
                    <ListBox Grid.Row="2" x:Name="ActivityList" BorderThickness="0" Foreground="#345572" FontSize="12"
                             ScrollViewer.HorizontalScrollBarVisibility="Disabled" IsTabStop="False">
                        <ListBox.ItemTemplate>
                            <DataTemplate>
                                <StackPanel Margin="1,5">
                                    <TextBlock Text="{Binding Heading}" FontWeight="SemiBold"/>
                                    <TextBlock Text="{Binding Details}" TextWrapping="Wrap" Foreground="#56718D"/>
                                </StackPanel>
                            </DataTemplate>
                        </ListBox.ItemTemplate>
                    </ListBox>
                    <Border Grid.Row="3" Background="#E8F5F3" CornerRadius="6" Padding="10" Margin="0,8,0,0">
                        <TextBlock x:Name="ExportStatus" Foreground="#1C645D" TextWrapping="Wrap" FontSize="12"/>
                    </Border>
                </Grid>
            </Border>
        </Grid>
        <DockPanel Grid.Row="3" LastChildFill="True" Margin="2,7,2,0">
            <TextBlock DockPanel.Dock="Right" Text="DISPATCH BOARD" FontSize="11" FontWeight="SemiBold" Foreground="#5A718A"
                       VerticalAlignment="Center"/>
            <TextBlock x:Name="StatusLine" Foreground="#345572" VerticalAlignment="Center" TextTrimming="CharacterEllipsis"/>
        </DockPanel>
    </Grid>
</Window>
'@

$window = [Windows.Markup.XamlReader]::Parse($xaml)
$ui = @{}
foreach ($name in @('ReleaseBadge', 'AcceptedMetric', 'RejectedMetric', 'HeldMetric', 'ImportButton',
        'HoldButton', 'ExportButton', 'SearchBox', 'QueueGrid', 'EmptyQueue', 'EmptyTitle', 'EmptyDetail',
        'Validation', 'ActivityList', 'ExportStatus', 'StatusLine')) {
    $ui[$name] = $window.FindName($name)
}

function Update-DispatchView {
    param([string]$SelectedId)

    $records = @($state.Records)
    $query = $ui.SearchBox.Text.Trim()
    $displayed = @($records | Where-Object {
        !$query -or "$($_.Id) $($_.Customer) $($_.Destination) $($_.Priority) $($_.Status)".IndexOf(
            $query, [StringComparison]::OrdinalIgnoreCase) -ge 0
    })
    $ui.QueueGrid.ItemsSource = $displayed
    if ($displayed.Count) {
        $selected = $displayed | Where-Object { $_.Id -eq $SelectedId } | Select-Object -First 1
        if (!$selected) {
            $selected = $displayed[0]
        }
        $ui.QueueGrid.SelectedItem = $selected
    }
    $ui.AcceptedMetric.Text = [string]$records.Count
    $ui.RejectedMetric.Text = [string]@($state.Rejected).Count
    $ui.HeldMetric.Text = [string]@($records | Where-Object { $_.Status -eq 'On Hold' }).Count
    $ui.HoldButton.IsEnabled = $displayed.Count -gt 0
    $ui.ExportButton.IsEnabled = $records.Count -gt 0
    $ui.EmptyQueue.Visibility = if ($displayed.Count) { 'Collapsed' } else { 'Visible' }
    $ui.EmptyTitle.Text = if ($query) { 'No matching shipments' } else { 'Queue is empty' }
    $ui.EmptyDetail.Text = if ($query) { 'Try a different customer, shipment or destination.' } else { 'Import the sample CSV to validate incoming shipments.' }
    $ui.Validation.Text = if ($state.Rejected.Count) {
        ($state.Rejected | Select-Object -First 2 | ForEach-Object { "$($_.Id)  $($_.Reason)" }) -join "`n"
    } elseif ($records.Count) {
        'CSV validation passed for all input rows.'
    } else {
        'Row validation results appear after import.'
    }
    $ui.ActivityList.ItemsSource = @($state.Events | Select-Object -Last 4 | Sort-Object At -Descending |
        ForEach-Object {
            [pscustomobject]@{ Heading = "$($_.Action)  /  $($_.Version)"; Details = $_.Details }
        })
    $ui.ExportStatus.Text = if ($state.LastExport) {
        "$($state.LastExport.File)`n$($state.LastExport.Written) exported / $($state.LastExport.Expected) queued"
    } else {
        'No manifest exported yet.'
    }
}

function Invoke-DispatchImport {
    $import = Read-DispatchInput
    $state.Records = $import.Records
    $state.Rejected = $import.Rejected
    $state.LastExport = $null
    $ui.SearchBox.Clear()
    $details = "$($state.Records.Count) accepted / $($state.Rejected.Count) rejected"
    Add-DispatchEvent -Action 'Import' -Details $details
    Update-DispatchView
    $ui.StatusLine.Text = "Import complete. $details."
}

function Invoke-DispatchHold {
    $selected = $ui.QueueGrid.SelectedItem
    if (!$selected) {
        return
    }
    $selected.Status = if ($selected.Status -eq 'On Hold') { 'Ready' } else { 'On Hold' }
    $details = "$($selected.Id) set to $($selected.Status)"
    Add-DispatchEvent -Action 'StatusChanged' -Details $details
    Update-DispatchView -SelectedId $selected.Id
    $ui.StatusLine.Text = "$details. Change saved."
}

function Invoke-DispatchExport {
    if (!$state.Records.Count) {
        return
    }
    $count = $state.Records.Count
    $manifest = @($state.Records)
    if ($Regression) {
        $manifest = @($manifest | Select-Object -First ($count - 1))
    }
    $lines = if ($manifest.Count) {
        @($manifest | Select-Object -Property $exportColumns | ConvertTo-Csv -NoTypeInformation)
    } else {
        ('"' + ($exportColumns -join '","') + '"')
    }
    [IO.File]::WriteAllLines($exportPath, [string[]]@($lines), $utf8)
    $state.LastExport = [ordered]@{ File = [IO.Path]::GetFileName($exportPath); Expected = $count; Written = $manifest.Count }
    $details = "$($manifest.Count) rows written to $($state.LastExport.File)"
    Add-DispatchEvent -Action 'Export' -Details $details
    Update-DispatchView
    $ui.StatusLine.Text = "Export complete. $details."
}

function Invoke-DispatchAction([scriptblock]$Action) {
    try {
        & $Action
    } catch {
        $ui.StatusLine.Text = $_.Exception.Message
        Write-Warning $_.Exception.Message
    }
}

$ui.ReleaseBadge.Text = "RELEASE $Version"
$launchDetails = if ($state.Records.Count) { "Restored $($state.Records.Count) shipments." } else { 'Opened a new shipment workspace.' }
Add-DispatchEvent -Action 'Launch' -Details $launchDetails
Update-DispatchView
$ui.StatusLine.Text = $launchDetails
$ui.ImportButton.Add_Click({ Invoke-DispatchAction { Invoke-DispatchImport } })
$ui.HoldButton.Add_Click({ Invoke-DispatchAction { Invoke-DispatchHold } })
$ui.ExportButton.Add_Click({ Invoke-DispatchAction { Invoke-DispatchExport } })
$ui.SearchBox.Add_TextChanged({ Update-DispatchView })
$window.Add_PreviewKeyDown({
    param($sender, $eventArgs)

    if ([Windows.Input.Keyboard]::Modifiers -eq [Windows.Input.ModifierKeys]::Control) {
        switch ($eventArgs.Key) {
            I { Invoke-DispatchAction { Invoke-DispatchImport } }
            H { Invoke-DispatchAction { Invoke-DispatchHold } }
            E { Invoke-DispatchAction { Invoke-DispatchExport } }
            F { $null = $ui.SearchBox.Focus() }
            default { return }
        }
        $eventArgs.Handled = $true
    }
})
$null = $window.ShowDialog()
