import { Inject, Injectable, OnModuleInit, UnauthorizedException } from "@nestjs/common";
import crypto from "crypto";
import { PrismaService } from "../../infrastructure/prisma/prisma.service";

const ITERATIONS = 120000;
const KEY_LENGTH = 32;
const DIGEST = "sha256";

@Injectable()
export class AuthService implements OnModuleInit {
  constructor(@Inject(PrismaService) private readonly prisma: PrismaService) {}

  async onModuleInit() {
    await this.prisma.ensureSchema();
    const username = process.env.OSLAB_WEB_ADMIN_USERNAME;
    const password = process.env.OSLAB_WEB_ADMIN_PASSWORD;
    if (!username || !password) {
      const count = await this.prisma.user.count();
      if (count > 0) return;
      // eslint-disable-next-line no-console
      console.warn("No web users exist. Set OSLAB_WEB_ADMIN_USERNAME and OSLAB_WEB_ADMIN_PASSWORD, then restart the API.");
      return;
    }
    await this.prisma.user.upsert({
      where: { username },
      create: { username, passwordHash: hashPassword(password), role: "admin" },
      update: { passwordHash: hashPassword(password), role: "admin" },
    });
  }

  async login(username: string, password: string) {
    const user = await this.prisma.user.findUnique({ where: { username } });
    if (!user || !verifyPassword(password, user.passwordHash)) {
      throw new UnauthorizedException("Invalid username or password");
    }
    const token = crypto.randomBytes(32).toString("hex");
    const expiresAt = new Date(Date.now() + 1000 * 60 * 60 * 12);
    await this.prisma.session.create({ data: { token, userId: user.id, expiresAt } });
    return { token, user: { id: user.id, username: user.username, role: user.role }, expiresAt };
  }

  async logout(token: string | undefined) {
    if (!token) return;
    await this.prisma.session.deleteMany({ where: { token } });
  }

  async authenticate(token: string | undefined) {
    if (!token) return null;
    const session = await this.prisma.session.findUnique({ where: { token }, include: { user: true } });
    if (!session || session.expiresAt.getTime() < Date.now()) return null;
    return { id: session.user.id, username: session.user.username, role: session.user.role };
  }
}

export function hashPassword(password: string): string {
  const salt = crypto.randomBytes(16).toString("hex");
  const hash = crypto.pbkdf2Sync(password, salt, ITERATIONS, KEY_LENGTH, DIGEST).toString("hex");
  return `${ITERATIONS}:${salt}:${hash}`;
}

export function verifyPassword(password: string, encoded: string): boolean {
  const [iterationsText, salt, expected] = encoded.split(":");
  const iterations = Number(iterationsText);
  if (!iterations || !salt || !expected) return false;
  const actual = crypto.pbkdf2Sync(password, salt, iterations, KEY_LENGTH, DIGEST).toString("hex");
  return crypto.timingSafeEqual(Buffer.from(actual, "hex"), Buffer.from(expected, "hex"));
}
