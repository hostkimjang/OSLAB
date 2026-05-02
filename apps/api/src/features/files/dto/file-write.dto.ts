import { IsString } from "class-validator";

export class FileWriteDto {
  @IsString()
  path!: string;

  @IsString()
  content!: string;
}
