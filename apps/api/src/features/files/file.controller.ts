import { Body, Controller, Get, Inject, Post, Put, Query, UseGuards } from "@nestjs/common";
import { AuthGuard } from "../../common/guards/auth.guard";
import { WorkspaceService } from "../../infrastructure/workspace/workspace.service";
import { FileCreateDto } from "./dto/file-create.dto";
import { FileReadQueryDto } from "./dto/file-read-query.dto";
import { FileWriteDto } from "./dto/file-write.dto";

@Controller("api/files")
@UseGuards(AuthGuard)
export class FileController {
  constructor(@Inject(WorkspaceService) private readonly workspace: WorkspaceService) {}

  @Get()
  async read(@Query() query: FileReadQueryDto) {
    return { path: query.path, content: await this.workspace.readText(query.path) };
  }

  @Put()
  async write(@Body() body: FileWriteDto) {
    await this.workspace.writeText(body.path, body.content);
    return { ok: true };
  }

  @Post()
  async create(@Body() body: FileCreateDto) {
    await this.workspace.createText(body.path, body.content);
    return { ok: true, path: body.path };
  }
}
