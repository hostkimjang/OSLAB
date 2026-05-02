import { Controller, Get, Inject, UseGuards } from "@nestjs/common";
import { AuthGuard } from "../../common/guards/auth.guard";
import { WorkspaceService } from "../../infrastructure/workspace/workspace.service";

@Controller("api/catalog")
@UseGuards(AuthGuard)
export class CatalogController {
  constructor(@Inject(WorkspaceService) private readonly workspace: WorkspaceService) {}

  @Get("scenarios")
  scenarios() {
    return this.workspace.listCatalog("scenario");
  }

  @Get("suites")
  suites() {
    return this.workspace.listCatalog("suite");
  }

  @Get("fixtures")
  fixtures() {
    return this.workspace.listCatalog("fixture");
  }

  @Get("artifacts")
  artifacts() {
    return this.workspace.listCatalog("artifact");
  }
}
