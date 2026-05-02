import "reflect-metadata";
import { ValidationPipe } from "@nestjs/common";
import { NestFactory } from "@nestjs/core";
import { existsSync, readFileSync } from "fs";
import path from "path";
import { AppModule } from "./app.module";

loadLocalEnv();

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  app.useGlobalPipes(new ValidationPipe({ whitelist: true, transform: true }));
  const webOrigin = process.env.OSLAB_WEB_ORIGIN ?? "http://localhost:3000";
  app.enableCors({
    origin: buildAllowedOrigins(webOrigin),
    credentials: true,
  });
  const host = process.env.OSLAB_WEB_HOST ?? "127.0.0.1";
  const port = Number(process.env.OSLAB_API_PORT ?? "3001");
  await app.listen(port, host);
  // eslint-disable-next-line no-console
  console.log(`oslab API listening on http://${host}:${port}`);
}

bootstrap().catch((error) => {
  // eslint-disable-next-line no-console
  console.error(error);
  process.exit(1);
});

function loadLocalEnv() {
  const envPath = path.resolve(process.cwd(), ".env");
  if (!existsSync(envPath)) return;
  const content = readFileSync(envPath, "utf8");
  for (const line of content.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) continue;
    const [key, ...rest] = trimmed.split("=");
    if (process.env[key]) continue;
    process.env[key] = rest.join("=").trim().replace(/^['"]|['"]$/g, "");
  }
}

function buildAllowedOrigins(primary: string): string[] {
  const values = new Set<string>([primary]);
  try {
    const url = new URL(primary);
    if (url.hostname === "localhost") {
      values.add(`${url.protocol}//127.0.0.1${url.port ? `:${url.port}` : ""}`);
    }
    if (url.hostname === "127.0.0.1") {
      values.add(`${url.protocol}//localhost${url.port ? `:${url.port}` : ""}`);
    }
  } catch {
    // Keep the primary origin only when parsing fails.
  }
  return [...values];
}
