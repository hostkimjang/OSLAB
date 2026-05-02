import { Module } from "@nestjs/common";
import { ArtifactModule } from "./features/artifacts/artifact.module";
import { AuthModule } from "./features/auth/auth.module";
import { BuilderModule } from "./features/builder/builder.module";
import { CatalogModule } from "./features/catalog/catalog.module";
import { FileModule } from "./features/files/file.module";
import { JobModule } from "./features/jobs/job.module";
import { LabModule } from "./features/lab/lab.module";
import { RunModule } from "./features/runs/run.module";
import { ValidationModule } from "./features/validation/validation.module";
import { PrismaModule } from "./infrastructure/prisma/prisma.module";
import { WorkspaceModule } from "./infrastructure/workspace/workspace.module";

@Module({
  imports: [
    PrismaModule,
    WorkspaceModule,
    AuthModule,
    BuilderModule,
    CatalogModule,
    FileModule,
    ValidationModule,
    ArtifactModule,
    JobModule,
    LabModule,
    RunModule,
  ],
})
export class AppModule {}
