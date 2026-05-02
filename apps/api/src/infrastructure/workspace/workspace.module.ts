import { Global, Module } from "@nestjs/common";
import { WorkspaceService } from "./workspace.service";

@Global()
@Module({
  providers: [WorkspaceService],
  exports: [WorkspaceService],
})
export class WorkspaceModule {}
