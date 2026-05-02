import { IsNumber, IsOptional, Min } from "class-validator";

export class JobTimeoutsDto {
  @IsOptional()
  @IsNumber()
  @Min(1)
  boot?: number;

  @IsOptional()
  @IsNumber()
  @Min(1)
  guest?: number;

  @IsOptional()
  @IsNumber()
  @Min(1)
  command?: number;

  @IsOptional()
  @IsNumber()
  @Min(0)
  pollInterval?: number;
}
