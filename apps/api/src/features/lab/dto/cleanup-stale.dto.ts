import { IsBoolean, IsOptional, IsString } from "class-validator";

export class CleanupStaleDto {
  @IsOptional()
  @IsString()
  scenarioPath?: string;

  @IsOptional()
  @IsString()
  configPath?: string;

  @IsOptional()
  @IsString()
  envFilePath?: string;

  @IsOptional()
  @IsBoolean()
  dryRun?: boolean;

  @IsOptional()
  @IsString()
  confirmToken?: string;

  @IsOptional()
  @IsBoolean()
  includeRunning?: boolean;
}
