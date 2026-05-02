import { IsString } from "class-validator";

export class FileCreateDto {
  @IsString()
  path = "";

  @IsString()
  content = "";
}
