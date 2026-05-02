import { Module } from "@nestjs/common";
import { ArtifactLanguageService } from "./artifact-language.service";
import { ArtifactController } from "./artifact.controller";

@Module({
  controllers: [ArtifactController],
  providers: [ArtifactLanguageService],
})
export class ArtifactModule {}
