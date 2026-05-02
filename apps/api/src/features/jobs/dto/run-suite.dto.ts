import { Type } from "class-transformer";
import { IsBoolean, IsNumber, IsOptional, IsString, Min, ValidateNested } from "class-validator";
import type { RunSuiteRequest } from "@oslab/shared";
import { JobTimeoutsDto } from "./job-timeouts.dto";

export class RunSuiteDto implements RunSuiteRequest {
  @IsString()
  suitePath!: string;

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
  @IsNumber()
  @Min(1)
  maxParallel?: number;

  @IsOptional()
  @ValidateNested()
  @Type(() => JobTimeoutsDto)
  timeouts?: JobTimeoutsDto;
}
