import { Body, Controller, Get, Inject, Post, Query, UseGuards } from "@nestjs/common";
import { AuthGuard } from "../../common/guards/auth.guard";
import { CleanupStaleDto } from "./dto/cleanup-stale.dto";
import { LabStatusQueryDto } from "./dto/lab-status-query.dto";
import { LabService } from "./lab.service";

@Controller("api/lab")
@UseGuards(AuthGuard)
export class LabController {
  constructor(@Inject(LabService) private readonly lab: LabService) {}

  @Get("status")
  status(@Query() query: LabStatusQueryDto) {
    return this.lab.status({
      scenarioPath: query.scenarioPath,
      configPath: query.configPath,
      envFilePath: query.envFilePath,
      requiredCapacity: query.requiredCapacity ? Number(query.requiredCapacity) : undefined,
    });
  }

  @Post("cleanup-stale")
  cleanupStale(@Body() body: CleanupStaleDto) {
    return this.lab.cleanupStale(body);
  }
}
