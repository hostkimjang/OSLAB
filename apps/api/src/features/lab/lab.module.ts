import { Module } from "@nestjs/common";
import { LabController } from "./lab.controller";
import { LabService } from "./lab.service";
import { ProxmoxLabClient } from "./proxmox-lab.client";

@Module({
  controllers: [LabController],
  providers: [LabService, ProxmoxLabClient],
  exports: [LabService],
})
export class LabModule {}
