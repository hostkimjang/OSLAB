import { Module } from "@nestjs/common";
import { WorkspaceModule } from "../../infrastructure/workspace/workspace.module";
import { ValidationController } from "./validation.controller";

@Module({
  imports: [WorkspaceModule],
  controllers: [ValidationController],
})
export class ValidationModule {}
