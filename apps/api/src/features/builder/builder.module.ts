import { Module } from "@nestjs/common";
import { WorkspaceModule } from "../../infrastructure/workspace/workspace.module";
import { BuilderController } from "./builder.controller";

@Module({
  imports: [WorkspaceModule],
  controllers: [BuilderController],
})
export class BuilderModule {}
