import { Module } from "@nestjs/common";
import { WorkspaceModule } from "../../infrastructure/workspace/workspace.module";
import { FileController } from "./file.controller";

@Module({
  imports: [WorkspaceModule],
  controllers: [FileController],
})
export class FileModule {}
