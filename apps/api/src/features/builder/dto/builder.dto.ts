import { IsArray, IsBoolean, IsInt, IsObject, IsOptional, IsString, Min } from "class-validator";

export type ScenarioCommandModel = {
  shell: string;
  template: string;
};

export type ScenarioFixtureModel = {
  id: string;
  type: string;
  source: string;
  expectedOutput: string;
};

export type ScenarioProductStepModel = {
  id: string;
  shell: string;
  template: string;
  captureStdoutJson: boolean;
  expectStdoutJsonJson: string;
  secretTokensJson: string;
};

export type ScenarioAssertionModel = {
  id: string;
  type: string;
  bodyJson: string;
};

export type ScenarioBuilderModel = {
  schemaVersion: number;
  id: string;
  name: string;
  osFamily: string;
  osVersion: string;
  template: string;
  templateVmId: number | null;
  vmIdStart: number | null;
  vmIdEnd: number | null;
  guestMode: string;
  windowsOrder: string[];
  linuxOrder: string[];
  artifactType: string;
  artifactPathParam: string;
  artifactDestination: string;
  artifactTransfer: string;
  artifactCommand: ScenarioCommandModel;
  outputActualPath: string;
  outputActualAdapter: string;
  reportFormats: string[];
  cleanupDestroyVm: boolean;
  cleanupKeepVmOnFailure: boolean;
  fixtures: ScenarioFixtureModel[];
  productSteps: ScenarioProductStepModel[];
  assertions: ScenarioAssertionModel[];
  fixtureCount: number;
  assertionCount: number;
};

export type SuiteBuilderRun = {
  id: string;
  scenario: string;
  tier: string;
  allowFailure: boolean;
  enabled: boolean;
};

export type SuiteBuilderModel = {
  schemaVersion: number;
  id: string;
  name: string;
  maxParallel: number | null;
  runs: SuiteBuilderRun[];
};

export class InspectBuilderDto {
  @IsString()
  content = "";
}

export class ScenarioTemplateDto {
  @IsString()
  kind = "windows-basic";

  @IsString()
  id = "";

  @IsString()
  name = "";

  @IsOptional()
  @IsString()
  path?: string;
}

export class FixtureTemplateDto {
  @IsString()
  kind = "powershell";

  @IsString()
  id = "";

  @IsOptional()
  @IsString()
  path?: string;
}

export class SuiteTemplateDto {
  @IsOptional()
  @IsString()
  kind?: string;

  @IsString()
  id = "";

  @IsString()
  name = "";

  @IsOptional()
  @IsString()
  scenarioPath?: string;

  @IsOptional()
  @IsArray()
  @IsString({ each: true })
  scenarioPaths?: string[];

  @IsOptional()
  @IsString()
  tier?: string;

  @IsOptional()
  @IsBoolean()
  allowFailure?: boolean;

  @IsOptional()
  @IsBoolean()
  enabled?: boolean;

  @IsOptional()
  @IsInt()
  @Min(1)
  maxParallel?: number;

  @IsOptional()
  @IsString()
  path?: string;
}

export class RenderScenarioDto {
  @IsString()
  content = "";

  @IsObject()
  model!: ScenarioBuilderModel;
}

export class RenderSuiteDto {
  @IsString()
  content = "";

  @IsObject()
  model!: SuiteBuilderModel;
}
