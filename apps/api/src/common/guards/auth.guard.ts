import { CanActivate, ExecutionContext, Inject, Injectable, UnauthorizedException } from "@nestjs/common";
import { parse } from "cookie";
import type { Request } from "express";
import { AuthService } from "../../features/auth/auth.service";

export interface AuthenticatedRequest extends Request {
  user?: { id: string; username: string; role: string };
  sessionToken?: string;
}

@Injectable()
export class AuthGuard implements CanActivate {
  constructor(@Inject(AuthService) private readonly auth: AuthService) {}

  async canActivate(context: ExecutionContext): Promise<boolean> {
    const request = context.switchToHttp().getRequest<AuthenticatedRequest>();
    const cookies = parse(request.headers.cookie ?? "");
    const token = cookies.oslab_session;
    const user = await this.auth.authenticate(token);
    if (!user) throw new UnauthorizedException("Authentication required");
    request.user = user;
    request.sessionToken = token;
    return true;
  }
}
