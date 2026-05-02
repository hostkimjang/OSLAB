import { IsOptional, IsString } from "class-validator";

export class LabStatusQueryDto {
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
  @IsString()
  requiredCapacity?: string;
}
