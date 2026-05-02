import { Body, Controller, Get, Inject, Param, Post, Res, UseGuards } from "@nestjs/common";
import type { Response } from "express";
import { AuthGuard } from "../../common/guards/auth.guard";
import { RunScenarioDto } from "./dto/run-scenario.dto";
import { RunSuiteDto } from "./dto/run-suite.dto";
import { JobService } from "./job.service";

@Controller("api/jobs")
@UseGuards(AuthGuard)
export class JobController {
  constructor(@Inject(JobService) private readonly jobs: JobService) {}

  @Post("run-scenario")
  runScenario(@Body() body: RunScenarioDto) {
    return this.jobs.runScenario(body);
  }

  @Post("run-suite")
  runSuite(@Body() body: RunSuiteDto) {
    return this.jobs.runSuite(body);
  }

  @Get()
  list() {
    return this.jobs.list();
  }

  @Get(":id")
  get(@Param("id") id: string) {
    return this.jobs.get(id);
  }

  @Post(":id/cancel")
  cancel(@Param("id") id: string) {
    return this.jobs.cancel(id);
  }

  @Get(":id/log")
  log(@Param("id") id: string) {
    return this.jobs.log(id).then((log) => ({ log }));
  }

  @Get(":id/events")
  async events(@Param("id") id: string, @Res() response: Response) {
    response.setHeader("Content-Type", "text/event-stream");
    response.setHeader("Cache-Control", "no-cache");
    response.setHeader("Connection", "keep-alive");
    response.setHeader("X-Accel-Buffering", "no");
    response.flushHeaders?.();
    response.write(": connected\n\n");
    const existing = await this.jobs.log(id);
    if (existing) {
      response.write(`event: log\ndata: ${JSON.stringify(existing)}\n\n`);
    }
    const unsubscribe = this.jobs.subscribe(id, (event) => {
      response.write(`event: ${event.type}\ndata: ${JSON.stringify(event.data)}\n\n`);
    });
    const heartbeat = setInterval(() => {
      response.write(": keepalive\n\n");
    }, 15000);
    response.on("close", () => {
      clearInterval(heartbeat);
      unsubscribe();
      response.end();
    });
  }
}
