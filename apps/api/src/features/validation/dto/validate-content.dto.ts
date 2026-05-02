import { IsString } from "class-validator";

export class ValidateContentDto {
  @IsString()
  path!: string;

  @IsString()
  content!: string;
}
