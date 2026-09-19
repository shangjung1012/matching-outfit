declare module '@mkkellogg/gaussian-splats-3d' {
  export const RenderMode: { OnChange: number }
  export const SceneFormat: { Ply: number }
  export class Viewer {
    constructor(options?: Record<string, unknown>)
    camera: any
    controls: any
    initialCameraPosition: any
    initialCameraLookAt: any
    cameraUp: any
    addSplatScene(path: string, options?: Record<string, unknown>): Promise<void>
    start(): void
    forceRenderNextFrame(): void
    dispose(): Promise<void>
  }
}
