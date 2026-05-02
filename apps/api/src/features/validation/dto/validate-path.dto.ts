import { IsString } from "class-validator";

export class ValidatePathDto {
  @IsString()
  path!: string;
}
