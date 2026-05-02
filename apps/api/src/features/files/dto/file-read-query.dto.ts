import { IsString } from "class-validator";

export class FileReadQueryDto {
  @IsString()
  path!: string;
}
