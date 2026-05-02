import { Module } from "@nestjs/common";
import { JobModule } from "../jobs/job.module";
import { RunController } from "./run.controller";

@Module({
  imports: [JobModule],
  controllers: [RunController],
})
export class RunModule {}
