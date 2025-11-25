'use client'

import { useState, useRef, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Input } from '@/components/ui/input'
import { Upload, FileText } from 'lucide-react'

interface Component {
  id: string
  type: string
  bounding_box: {
    x: number
    y: number
    width: number
    height: number
  }
  confidence?: number
}

interface ComparisonMetrics {
  difference_count: number
  match_rate: number
  total_components: number
  completeness: number
}

interface ComparisonResult {
  matches: Array<{
    design_component: Component
    code_component: Component
    iou: number
  }>
  unmatched_design: Component[]
  unmatched_code: Component[]
  total_design_components: number
  total_code_components: number
  matched_components: number
  unmatched_design_count: number
  unmatched_code_count: number
}

export default function DesignComparisonTool() {
  const [designJson, setDesignJson] = useState<string>('')
  const [codeJson, setCodeJson] = useState<string>('')
  const [metrics, setMetrics] = useState<ComparisonMetrics | null>(null)
  const [comparisonResult, setComparisonResult] = useState<ComparisonResult | null>(null)
  const [aiSuggestion, setAiSuggestion] = useState<string>('')
  const [userQuestion, setUserQuestion] = useState<string>('')
  const [isLoading, setIsLoading] = useState<boolean>(false)
  const [designComponents, setDesignComponents] = useState<Component[]>([])
  const [codeComponents, setCodeComponents] = useState<Component[]>([])
  const [designScreen, setDesignScreen] = useState<{ width: number; height: number } | undefined>(undefined)
  const [codeScreen, setCodeScreen] = useState<{ width: number; height: number } | undefined>(undefined)
  type Blueprint = {
    plan_id: string
    target_file: string
    confidence: string
    action_type: string
    location_hint: Record<string, any>
    reasoning: string
    parent_container_path?: string | null
  }
  const [blueprints, setBlueprints] = useState<Blueprint[]>([])
  const [reportId, setReportId] = useState<string>('')

  const designFileInputRef = useRef<HTMLInputElement>(null)
  const codeFileInputRef = useRef<HTMLInputElement>(null)
  const designCanvasRef = useRef<HTMLCanvasElement>(null)
  const codeCanvasRef = useRef<HTMLCanvasElement>(null)

  const handleFileUpload = (file: File, type: 'design' | 'code') => {
    const reader = new FileReader()
    reader.onload = (e) => {
      const content = e.target?.result as string
      if (type === 'design') {
        setDesignJson(content)
        const comps = extractComponents(content)
        setDesignComponents(comps)
        setDesignScreen(getScreenSize(content))
        if (designCanvasRef.current) {
          drawComponentsOnCanvas(designCanvasRef.current, comps, '#ff003c', undefined, getScreenSize(content))
        }
      } else {
        setCodeJson(content)
        const comps = extractComponents(content)
        setCodeComponents(comps)
        setCodeScreen(getScreenSize(content))
        if (codeCanvasRef.current) {
          drawComponentsOnCanvas(codeCanvasRef.current, comps, '#00f3ff', undefined, getScreenSize(content))
        }
      }
    }
    reader.readAsText(file)
  }

  function extractComponents(input: string | object): Component[] {
    let data: any
    try {
      data = typeof input === 'string' ? JSON.parse(input) : input
    } catch {
      return []
    }

    const result: Component[] = []

    function parseBounds(bounds: any) {
      const m = String(bounds).match(/-?\d+/g)
      if (!m || m.length < 4) return null
      const x1 = parseInt(m[0], 10)
      const y1 = parseInt(m[1], 10)
      const x2 = parseInt(m[2], 10)
      const y2 = parseInt(m[3], 10)
      const w = Math.max(0, x2 - x1)
      const h = Math.max(0, y2 - y1)
      return { x: x1, y: y1, width: w, height: h }
    }

    function recurse(node: any) {
      if (!node) return
      if (Array.isArray(node)) {
        node.forEach(recurse)
        return
      }
      if (typeof node === 'object') {
        const attrs = node.attributes
        if (attrs && typeof attrs === 'object') {
          const bb = parseBounds(attrs.bounds)
          const type = attrs.type || 'component'
          if (bb && type !== 'root' && bb.width > 0 && bb.height > 0) {
            const id = attrs.accessibilityId || attrs.hashcode || `${result.length}`
            const comp: Component = {
              id: String(id),
              type,
              bounding_box: bb,
            }
            result.push(comp)
          }
        }
        const children = node.children
        if (Array.isArray(children)) children.forEach(recurse)
      }
    }

    recurse(data)
    return result
  }

  const drawComponentsOnCanvas = (
    canvas: HTMLCanvasElement,
    components: Component[],
    color: string,
    unmatchedComponents?: Component[],
    screen?: { width: number; height: number }
  ) => {
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const container = canvas.parentElement as HTMLElement | null
    const containerRect = container?.getBoundingClientRect()
    const targetW = containerRect?.width ?? 640
    const viewportH = window.innerHeight || 800
    const safeMargin = 240
    const targetHCap = Math.max(300, viewportH - safeMargin)
    const srcW = screen?.width ?? 640
    const srcH = screen?.height ?? 420
    const scale = Math.min(targetW / Math.max(1, srcW), targetHCap / Math.max(1, srcH))
    const CANVAS_W = Math.max(1, Math.floor(srcW * scale))
    const CANVAS_H = Math.max(1, Math.floor(srcH * scale))
    const dpr = window.devicePixelRatio || 1
    canvas.style.width = `${CANVAS_W}px`
    canvas.style.height = `${CANVAS_H}px`
    canvas.width = Math.floor(CANVAS_W * dpr)
    canvas.height = Math.floor(CANVAS_H * dpr)
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, CANVAS_W, CANVAS_H)

    // Dark background for canvas
    ctx.fillStyle = '#0a0a0a'
    ctx.fillRect(0, 0, CANVAS_W, CANVAS_H)

    // Grid lines
    ctx.strokeStyle = '#1a1a1a'
    ctx.lineWidth = 1
    const gridSize = 20
    for (let x = 0; x < CANVAS_W; x += gridSize) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, CANVAS_H); ctx.stroke();
    }
    for (let y = 0; y < CANVAS_H; y += gridSize) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(CANVAS_W, y); ctx.stroke();
    }

    const all = [...(components || []), ...((unmatchedComponents || []))]
    if (all.length === 0) return

    if (components) {
      ctx.strokeStyle = color
      ctx.shadowColor = color
      ctx.shadowBlur = 4
      const baseW = 1
      const lineW = Math.max(0.5, (baseW * scale) / dpr)
      ctx.lineWidth = lineW
      ctx.setLineDash([Math.max(1, Math.round(6 * scale)), Math.max(1, Math.round(3 * scale))])
      components.forEach(component => {
        const { x, y, width, height } = component.bounding_box
        ctx.strokeRect(x * scale, y * scale, width * scale, height * scale)
      })
      ctx.shadowBlur = 0
    }

    if (unmatchedComponents && unmatchedComponents.length) {
      ctx.strokeStyle = color === '#ff003c' ? '#ff4444' : '#4444ff'
      const baseW = 0.75
      const lineW = Math.max(0.5, (baseW * scale) / dpr)
      ctx.lineWidth = lineW
      ctx.setLineDash([Math.max(1, Math.round(4 * scale)), Math.max(1, Math.round(2 * scale))])
      unmatchedComponents.forEach(component => {
        const { x, y, width, height } = component.bounding_box
        ctx.strokeRect(x * scale, y * scale, width * scale, height * scale)
      })
    }
  }

  useEffect(() => {
    if (designCanvasRef.current) {
      const screen = getScreenSize(designJson)
      drawComponentsOnCanvas(designCanvasRef.current, designComponents, '#ff003c', undefined, screen)
    }
  }, [designComponents])

  useEffect(() => {
    if (codeCanvasRef.current) {
      const screen = getScreenSize(codeJson)
      drawComponentsOnCanvas(codeCanvasRef.current, codeComponents, '#00f3ff', undefined, screen)
    }
  }, [codeComponents])

  const compareDesigns = async () => {
    if (!designJson || !codeJson) {
      alert('请上传两个JSON文件')
      return
    }

    setIsLoading(true)
    try {
      const response = await fetch('http://localhost:5050/api/compare', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          design_json: designJson,
          code_json: codeJson,
        }),
      })

      const data = await response.json()
      if (data.success) {
        setComparisonResult(data.comparison_result)
        setBlueprints(data.ai_blueprints || [])
        setReportId(data.diagnostic_report?.report_id || '')
        if (data.screen) {
          setDesignScreen(data.screen)
          setCodeScreen(data.screen)
        }
        if (designCanvasRef.current) {
          drawComponentsOnCanvas(
            designCanvasRef.current,
            designComponents,
            '#ff003c',
            undefined,
            data.screen || getScreenSize(designJson)
          )
        }
        if (codeCanvasRef.current) {
          drawComponentsOnCanvas(
            codeCanvasRef.current,
            codeComponents,
            '#00f3ff',
            undefined,
            data.screen || getScreenSize(codeJson)
          )
        }
      } else {
        alert('比较失败: ' + data.error)
      }
    } catch (error) {
      console.error('Error comparing designs:', error)
      alert('比较失败，请检查后端服务是否运行')
    } finally {
      setIsLoading(false)
    }
  }

  function getScreenSize(input: string | object | null): { width: number; height: number } | undefined {
    if (!input) return undefined
    let data: any
    try {
      data = typeof input === 'string' ? JSON.parse(input) : input
    } catch {
      return undefined
    }
    const attrs = data?.attributes
    const bounds = attrs?.bounds
    if (!bounds) return undefined
    const m = String(bounds).match(/-?\d+/g)
    if (!m || m.length < 4) return undefined
    const x1 = parseInt(m[0], 10)
    const y1 = parseInt(m[1], 10)
    const x2 = parseInt(m[2], 10)
    const y2 = parseInt(m[3], 10)
    return { width: Math.max(0, x2 - x1), height: Math.max(0, y2 - y1) }
  }

  const sendQuestion = async () => {
    if (!userQuestion.trim()) return

    // Simulate AI response
    const mockResponse = `关于"${userQuestion}"，建议检查组件的定位精度和尺寸一致性，确保使用相同的布局算法。`
    setAiSuggestion(mockResponse)
    setUserQuestion('')
  }

  return (
    <div className="min-h-screen p-6 animate-fade-in-up">
      <div className="max-w-7xl mx-auto">
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-4xl font-bold text-primary mb-2 drop-shadow-[0_0_10px_rgba(0,243,255,0.5)]">
              设计对比工具 <span className="text-sm font-mono text-muted-foreground ml-2">v2.0.0</span>
            </h1>
            <p className="text-muted-foreground">Design vs Code Visual Comparison System</p>
          </div>
          <div className="flex items-center gap-2">
            <Button onClick={() => designFileInputRef.current?.click()} variant="outline" className="border-primary/50 hover:bg-primary/10 text-primary">
              <Upload className="mr-2 h-4 w-4" />
              上传原始设计JSON
            </Button>
            <Button onClick={() => codeFileInputRef.current?.click()} variant="outline" className="border-primary/50 hover:bg-primary/10 text-primary">
              <Upload className="mr-2 h-4 w-4" />
              上传代码生成JSON
            </Button>
            <Input
              type="file"
              accept=".json"
              ref={designFileInputRef}
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) handleFileUpload(file, 'design')
              }}
              className="hidden"
            />
            <Input
              type="file"
              accept=".json"
              ref={codeFileInputRef}
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) handleFileUpload(file, 'code')
              }}
              className="hidden"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
              <Card className="p-4 tech-border bg-card/50">
                <div className="flex items-center justify-between mb-4">
                  <span className="bg-destructive/20 text-destructive border border-destructive/50 px-3 py-1 rounded text-sm font-medium flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-destructive animate-pulse" />
                    原设计图
                  </span>
                </div>
                <div className="border border-border/50 rounded-lg bg-black/50 relative overflow-hidden w-full min-h-[300px] flex items-center justify-center">
                  <div className="animate-scanline opacity-20"></div>
                  <canvas ref={designCanvasRef} className="mx-auto block relative z-20" />
                  {!designJson && <div className="text-muted-foreground text-sm">等待上传...</div>}
                </div>
              </Card>
              <Card className="p-4 tech-border bg-card/50">
                <div className="flex items-center justify-between mb-4">
                  <span className="bg-primary/20 text-primary border border-primary/50 px-3 py-1 rounded text-sm font-medium flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
                    代码生成图
                  </span>
                </div>
                <div className="border border-border/50 rounded-lg bg-black/50 relative overflow-hidden w-full min-h-[300px] flex items-center justify-center">
                  <div className="animate-scanline opacity-20"></div>
                  <canvas ref={codeCanvasRef} className="mx-auto block relative z-20" />
                  {!codeJson && <div className="text-muted-foreground text-sm">等待上传...</div>}
                </div>
              </Card>
            </div>
            <div className="text-center mb-6">
              <Button
                onClick={compareDesigns}
                disabled={isLoading || !designJson || !codeJson}
                className="bg-primary text-primary-foreground hover:bg-primary/80 px-8 py-6 text-lg font-bold tracking-wider shadow-[0_0_20px_rgba(0,243,255,0.3)] transition-all hover:scale-105"
              >
                {isLoading ? '分析中...' : '开始比较分析'}
              </Button>
            </div>
          </div>
          <div className="lg:col-span-1">
            <Card className="p-6 tech-border bg-card/50">
              <h2 className="text-xl font-semibold text-primary mb-4 flex items-center">
                <FileText className="mr-2 h-5 w-5" />
                Planner 报告
              </h2>
              {reportId && (
                <div className="text-xs text-muted-foreground mb-2">报告ID：{reportId}</div>
              )}
              {blueprints && blueprints.length > 0 ? (
                <div className="space-y-3">
                  {blueprints.map((bp) => (
                    <div key={bp.plan_id} className="bg-secondary/50 border border-border p-4 rounded-lg">
                      <div className="flex items-center justify-between mb-2">
                        <div className="text-sm font-medium">{bp.plan_id}</div>
                        <span className="px-2 py-0.5 rounded text-xs border" >{bp.confidence}</span>
                      </div>
                      <div className="flex items-center gap-2 text-sm mb-2">
                        <span className="px-2 py-0.5 rounded bg-primary/20 text-primary border border-primary/50">{bp.action_type}</span>
                        <span className="font-mono text-xs text-muted-foreground">{bp.target_file || '未知文件'}</span>
                      </div>
                      <div className="text-xs font-mono text-muted-foreground mb-2">{bp.reasoning}</div>
                      {bp.location_hint && (
                        <div className="text-xs font-mono bg-black/40 border border-border rounded p-2 overflow-x-auto">
                          {Object.keys(bp.location_hint).map((k) => (
                            <div key={k} className="flex gap-2"><span className="text-muted-foreground">{k}:</span><span>{String(bp.location_hint[k])}</span></div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-muted-foreground text-center py-8 border border-dashed border-border rounded-lg">
                  <p>无可用蓝图</p>
                  <p className="text-xs opacity-50">上传数据并开始分析以生成报告</p>
                </div>
              )}
            </Card>
          </div>
        </div>
      </div>
    </div>
  )
}
