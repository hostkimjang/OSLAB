import { Body, Controller, Get, Inject, Post, Req, Res, UseGuards } from "@nestjs/common";
import { parse } from "cookie";
import type { Response } from "express";
import { AuthGuard, AuthenticatedRequest } from "../../common/guards/auth.guard";
import { LoginDto } from "./dto/login.dto";
import { AuthService } from "./auth.service";

@Controller("api")
export class AuthController {
  constructor(@Inject(AuthService) private readonly auth: AuthService) {}

  @Post("auth/login")
  async login(@Body() body: LoginDto, @Res({ passthrough: true }) response: Response) {
    const result = await this.auth.login(String(body.username ?? ""), String(body.password ?? ""));
    response.cookie("oslab_session", result.token, {
      httpOnly: true,
      sameSite: "lax",
      expires: result.expiresAt,
      path: "/",
    });
    return { user: result.user };
  }

  @Post("auth/logout")
  @UseGuards(AuthGuard)
  async logout(@Req() request: AuthenticatedRequest, @Res({ passthrough: true }) response: Response) {
    await this.auth.logout(request.sessionToken);
    response.clearCookie("oslab_session", { path: "/" });
    return { ok: true };
  }

  @Get("me")
  async me(@Req() request: AuthenticatedRequest) {
    const cookies = parse(request.headers.cookie ?? "");
    const user = await this.auth.authenticate(cookies.oslab_session);
    return { user };
  }
}
