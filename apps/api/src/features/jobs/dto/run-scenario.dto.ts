import { Type } from "class-transformer";
import { IsBoolean, IsOptional, IsString, ValidateNested } from "class-validator";
import type { RunScenarioRequest } from "@oslab/shared";
import { JobTimeoutsDto } from "./job-timeouts.dto";

export class RunScenarioDto implements RunScenarioRequest {
  @IsString()
  scenarioPath!: string;

  @IsOptional()
  @IsString()
  configPath?: string;

  @IsOptional()
  @IsString()
  envFilePath?: string;

  @IsOptional()
  @IsString()
  artifactPath?: string;

  @IsOptional()
  @IsString()
  uploadedArtifactId?: string | null;

  @IsOptional()
  @IsString()
  runId?: string;

  @IsOptional()
  @IsBoolean()
  keepVm?: boolean;

  @IsOptional()
  @IsBoolean()
  fullClone?: boolean;

  @IsOptional()
  @ValidateNested()
  @Type(() => JobTimeoutsDto)
  timeouts?: JobTimeoutsDto;
}
