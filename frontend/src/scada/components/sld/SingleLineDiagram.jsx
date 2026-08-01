/**
 * SingleLineDiagram.jsx — SCADA Single-Line Diagram
 * ==================================================
 * SVG-based fixed-topology diagram of the 11kV/0.4kV substation.
 * All measurements are live from scadaStore (updated every 5 seconds).
 *
 * Topology (viewBox 940 × 500):
 *
 *   [F1]─[CB1]──[BUS_A (11kV)]══[CB3]══[BUS_B (11kV)]─[CB2]─[F2]
 *                    │                        │
 *                  [CB4]                    [CB5]
 *                    │                        │
 *                  [TX1]                    [TX2]
 *                    │                        │
 *               [BUS_C (0.4kV)]         [BUS_D (0.4kV)]
 *               /            \           /           \
 *            [CB6]          [CB7]     [CB8]         [CB9]
 *              │              │         │              │
 *           [Load1]         [PV1]    [Load2]        [Load3]
 *
 * Energisation is derived from breaker states — open breakers cause
 * downstream elements to render in grey (de-energised colour).
 *
 * Phase 3 will add onClick handlers to breakers for control dialogs.
 */

import { useMemo } from 'react'
import { useScadaStore } from '../../store/scadaStore'
import {
  Busbar, CircuitBreaker, Transformer, Wire,
  LoadSymbol, PvSymbol, FeederArrow, MeasurementTag,
  voltageColour, loadingColour, energisedColour,
} from './SldElements'

// ─────────────────────────────────────────────────────────────────────────────
// LAYOUT CONSTANTS  (all in SVG user units, viewBox 940 × 500)
// ─────────────────────────────────────────────────────────────────────────────

const VB_W = 940
const VB_H = 500

// HV busbar Y position
const HV_Y = 160
// HV busbar X extents
const BUS_A_X1 = 130
const BUS_A_X2 = 390
const BUS_B_X1 = 550
const BUS_B_X2 = 810

// Busbar centre X positions
const BUS_A_CX = (BUS_A_X1 + BUS_A_X2) / 2   // 260
const BUS_B_CX = (BUS_B_X1 + BUS_B_X2) / 2   // 680

// Bus coupler CB3
const CB3_CX = (BUS_A_X2 + BUS_B_X1) / 2      // 470
const CB3_CY = HV_Y

// Feeder entry points (top of diagram)
const F1_CX = BUS_A_CX
const F2_CX = BUS_B_CX
const FEEDER_TOP_Y = 52

// CB1, CB2 (feeder breakers)
const CB1_CX = F1_CX
const CB1_CY = 110
const CB2_CX = F2_CX
const CB2_CY = 110

// Transformer vertical positions
const CB4_CY = 215   // CB between Bus A and TX1
const TX1_CY = 280
const CB5_CY = 215
const TX2_CY = 280

// LV busbar Y
const LV_Y = 345
const BUS_C_X1 = 110
const BUS_C_X2 = 390
const BUS_D_X1 = 550
const BUS_D_X2 = 830

const BUS_C_CX = (BUS_C_X1 + BUS_C_X2) / 2   // 250
const BUS_D_CX = (BUS_D_X1 + BUS_D_X2) / 2   // 690

// LV feeders
const CB6_CX = 185;  const CB6_CY = 395
const CB7_CX = 335;  const CB7_CY = 395
const CB8_CX = 605;  const CB8_CY = 395
const CB9_CX = 755;  const CB9_CY = 395

const LOAD_Y = 450
const PV_Y   = 450

// ─────────────────────────────────────────────────────────────────────────────
// ENERGISATION LOGIC
// Mirrors backend data_source._is_energised() so colours update instantly
// when breaker states change (before next server tick arrives).
// ─────────────────────────────────────────────────────────────────────────────

function computeEnergisation(bs) {
  const cb = (id) => bs[id] === 'CLOSED'

  const busA = cb('CB1')
  const busB = cb('CB2') || (cb('CB3') && busA)
  const busC = busA && cb('CB4')
  const busD = busB && cb('CB5')

  return {
    busA, busB, busC, busD,
    feeder1:  cb('CB1'),
    feeder2:  cb('CB2'),
    coupler:  busA && busB && cb('CB3'),
    tx1:      busA && cb('CB4'),
    tx2:      busB && cb('CB5'),
    load1:    busC && cb('CB6'),
    pv1:      busC && cb('CB7'),
    load2:    busD && cb('CB8'),
    load3:    busD && cb('CB9'),
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// MAIN COMPONENT
// ─────────────────────────────────────────────────────────────────────────────

export default function SingleLineDiagram({ onBreakerClick }) {
  const { buses, branches, transformers, breakerStates } = useScadaStore()

  const en = useMemo(
    () => computeEnergisation(breakerStates),
    [breakerStates],
  )

  // Shorthand accessors with safe defaults
  const busA  = buses['BUS_A']  ?? {}
  const busB  = buses['BUS_B']  ?? {}
  const busC  = buses['BUS_C']  ?? {}
  const busD  = buses['BUS_D']  ?? {}
  const tx1   = transformers['TX1'] ?? {}
  const tx2   = transformers['TX2'] ?? {}
  const f1    = branches['FEEDER1'] ?? {}
  const f2    = branches['FEEDER2'] ?? {}

  // Wire colours derived from energisation
  const wA  = energisedColour(en.busA)
  const wB  = energisedColour(en.busB)
  const wC  = energisedColour(en.busC)
  const wD  = energisedColour(en.busD)
  const wT1 = energisedColour(en.tx1)
  const wT2 = energisedColour(en.tx2)

  return (
    <div className="bg-[#0c1220] border border-[#1e293b] rounded overflow-hidden">
      {/* Diagram title bar */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-[#1e293b]">
        <span className="text-[10px] font-bold tracking-widest text-[#475569] uppercase">
          Single-Line Diagram — 11kV / 0.4kV Substation
        </span>
        <span className="text-[10px] text-[#334155] font-mono">
          IEC 60617
        </span>
      </div>

      <svg
        viewBox={`0 0 ${VB_W} ${VB_H}`}
        width="100%"
        style={{ display: 'block', maxHeight: '500px' }}
        fontFamily="monospace"
      >
        {/* ── Background grid (subtle) ──────────────────────────────────── */}
        <defs>
          <pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">
            <path d="M 20 0 L 0 0 0 20" fill="none" stroke="#1e293b" strokeWidth="0.5" />
          </pattern>
        </defs>
        <rect width={VB_W} height={VB_H} fill="url(#grid)" opacity={0.4} />

        {/* ══════════════════════════════════════════════════════════════════
            FEEDER 1 (left side)
        ══════════════════════════════════════════════════════════════════ */}
        <FeederArrow
          cx={F1_CX} cy={FEEDER_TOP_Y}
          colour={wA}
          label="FEEDER 1 · 11kV"
          current={f1.current_a}
        />
        {/* Wire: feeder arrow → CB1 */}
        <Wire x1={F1_CX} y1={FEEDER_TOP_Y + 10} x2={CB1_CX} y2={CB1_CY - 7} colour={wA} />
        <CircuitBreaker cx={CB1_CX} cy={CB1_CY} closed={breakerStates['CB1'] === 'CLOSED'} label="CB1" onClick={() => onBreakerClick('CB1')} />
        {/* Wire: CB1 → Bus A */}
        <Wire x1={CB1_CX} y1={CB1_CY + 7} x2={CB1_CX} y2={HV_Y} colour={wA} />

        {/* ══════════════════════════════════════════════════════════════════
            FEEDER 2 (right side)
        ══════════════════════════════════════════════════════════════════ */}
        <FeederArrow
          cx={F2_CX} cy={FEEDER_TOP_Y}
          colour={wB}
          label="FEEDER 2 · 11kV"
          current={f2.current_a}
        />
        <Wire x1={F2_CX} y1={FEEDER_TOP_Y + 10} x2={CB2_CX} y2={CB2_CY - 7} colour={wB} />
        <CircuitBreaker cx={CB2_CX} cy={CB2_CY} closed={breakerStates['CB2'] === 'CLOSED'} label="CB2" onClick={() => onBreakerClick('CB2')} />
        <Wire x1={CB2_CX} y1={CB2_CY + 7} x2={CB2_CX} y2={HV_Y} colour={wB} />

        {/* ══════════════════════════════════════════════════════════════════
            HV BUSBARS  (Bus A and Bus B)
        ══════════════════════════════════════════════════════════════════ */}
        <Busbar
          x={BUS_A_X1} y={HV_Y} width={BUS_A_X2 - BUS_A_X1}
          colour={voltageColour(busA.voltage_pu)}
          label="BUS A"
          voltage={busA.voltage_pu ? `${busA.voltage_pu.toFixed(4)} pu` : ''}
        />
        <Busbar
          x={BUS_B_X1} y={HV_Y} width={BUS_B_X2 - BUS_B_X1}
          colour={voltageColour(busB.voltage_pu)}
          label="BUS B"
          voltage={busB.voltage_pu ? `${busB.voltage_pu.toFixed(4)} pu` : ''}
        />

        {/* ══════════════════════════════════════════════════════════════════
            BUS COUPLER  CB3
        ══════════════════════════════════════════════════════════════════ */}
        {/* Wire A end → CB3 */}
        <Wire x1={BUS_A_X2} y1={HV_Y} x2={CB3_CX - 7} y2={CB3_CY} colour={wA} />
        <CircuitBreaker
          cx={CB3_CX} cy={CB3_CY}
          closed={breakerStates['CB3'] === 'CLOSED'}
          label="CB3"
          onClick={() => onBreakerClick('CB3')}
        />
        {/* Wire CB3 → B start */}
        <Wire x1={CB3_CX + 7} y1={CB3_CY} x2={BUS_B_X1} y2={HV_Y} colour={wB} />

        {/* CB3 label above (already in CircuitBreaker but add NOP label below) */}
        <text x={CB3_CX} y={HV_Y + 20} fill="#475569" fontSize={8} fontFamily="monospace" textAnchor="middle">
          COUPLER
        </text>

        {/* ══════════════════════════════════════════════════════════════════
            TX1 BRANCH  (Bus A → TX1 → Bus C)
        ══════════════════════════════════════════════════════════════════ */}
        {/* Drop from Bus A down to CB4 */}
        <Wire x1={BUS_A_CX} y1={HV_Y} x2={BUS_A_CX} y2={CB4_CY - 7} colour={wA} />
        <CircuitBreaker cx={BUS_A_CX} cy={CB4_CY} closed={breakerStates['CB4'] === 'CLOSED'} label="CB4" onClick={() => onBreakerClick('CB4')} />
        {/* CB4 → TX1 */}
        <Wire x1={BUS_A_CX} y1={CB4_CY + 7} x2={BUS_A_CX} y2={TX1_CY - 16} colour={wT1} />
        <Transformer
          cx={BUS_A_CX} cy={TX1_CY}
          colour={loadingColour(tx1.loading_pct)}
          label="TX1  630kVA"
          loading={tx1.loading_pct}
        />
        {/* TX1 → Bus C */}
        <Wire x1={BUS_A_CX} y1={TX1_CY + 16} x2={BUS_A_CX} y2={LV_Y} colour={wC} />

        {/* ══════════════════════════════════════════════════════════════════
            TX2 BRANCH  (Bus B → TX2 → Bus D)
        ══════════════════════════════════════════════════════════════════ */}
        <Wire x1={BUS_B_CX} y1={HV_Y} x2={BUS_B_CX} y2={CB5_CY - 7} colour={wB} />
        <CircuitBreaker cx={BUS_B_CX} cy={CB5_CY} closed={breakerStates['CB5'] === 'CLOSED'} label="CB5" onClick={() => onBreakerClick('CB5')} />
        <Wire x1={BUS_B_CX} y1={CB5_CY + 7} x2={BUS_B_CX} y2={TX2_CY - 16} colour={wT2} />
        <Transformer
          cx={BUS_B_CX} cy={TX2_CY}
          colour={loadingColour(tx2.loading_pct)}
          label="TX2  630kVA"
          loading={tx2.loading_pct}
        />
        <Wire x1={BUS_B_CX} y1={TX2_CY + 16} x2={BUS_B_CX} y2={LV_Y} colour={wD} />

        {/* ══════════════════════════════════════════════════════════════════
            LV BUSBARS  (Bus C and Bus D)
        ══════════════════════════════════════════════════════════════════ */}
        <Busbar
          x={BUS_C_X1} y={LV_Y} width={BUS_C_X2 - BUS_C_X1}
          colour={voltageColour(busC.voltage_pu)}
          label="BUS C"
          voltage={busC.voltage_pu ? `${busC.voltage_pu.toFixed(4)} pu` : ''}
        />
        <Busbar
          x={BUS_D_X1} y={LV_Y} width={BUS_D_X2 - BUS_D_X1}
          colour={voltageColour(busD.voltage_pu)}
          label="BUS D"
          voltage={busD.voltage_pu ? `${busD.voltage_pu.toFixed(4)} pu` : ''}
        />

        {/* ══════════════════════════════════════════════════════════════════
            LV FEEDERS — Bus C side
        ══════════════════════════════════════════════════════════════════ */}
        {/* CB6 → Load 1 */}
        <Wire x1={CB6_CX} y1={LV_Y} x2={CB6_CX} y2={CB6_CY - 7} colour={wC} />
        <CircuitBreaker cx={CB6_CX} cy={CB6_CY} closed={breakerStates['CB6'] === 'CLOSED'} label="CB6" onClick={() => onBreakerClick('CB6')} />
        <Wire x1={CB6_CX} y1={CB6_CY + 7} x2={CB6_CX} y2={LOAD_Y - 7} colour={energisedColour(en.load1)} />
        <LoadSymbol cx={CB6_CX} cy={LOAD_Y} colour={energisedColour(en.load1)} label="Load 1" />

        {/* CB7 → PV 1 */}
        <Wire x1={CB7_CX} y1={LV_Y} x2={CB7_CX} y2={CB7_CY - 7} colour={wC} />
        <CircuitBreaker cx={CB7_CX} cy={CB7_CY} closed={breakerStates['CB7'] === 'CLOSED'} label="CB7" onClick={() => onBreakerClick('CB7')} />
        <Wire x1={CB7_CX} y1={CB7_CY + 7} x2={CB7_CX} y2={PV_Y - 14} colour={energisedColour(en.pv1)} />
        <PvSymbol cx={CB7_CX} cy={PV_Y} colour={energisedColour(en.pv1)} label="PV 1" />

        {/* ══════════════════════════════════════════════════════════════════
            LV FEEDERS — Bus D side
        ══════════════════════════════════════════════════════════════════ */}
        {/* CB8 → Load 2 */}
        <Wire x1={CB8_CX} y1={LV_Y} x2={CB8_CX} y2={CB8_CY - 7} colour={wD} />
        <CircuitBreaker cx={CB8_CX} cy={CB8_CY} closed={breakerStates['CB8'] === 'CLOSED'} label="CB8" onClick={() => onBreakerClick('CB8')} />
        <Wire x1={CB8_CX} y1={CB8_CY + 7} x2={CB8_CX} y2={LOAD_Y - 7} colour={energisedColour(en.load2)} />
        <LoadSymbol cx={CB8_CX} cy={LOAD_Y} colour={energisedColour(en.load2)} label="Load 2" />

        {/* CB9 → Load 3 */}
        <Wire x1={CB9_CX} y1={LV_Y} x2={CB9_CX} y2={CB9_CY - 7} colour={wD} />
        <CircuitBreaker cx={CB9_CX} cy={CB9_CY} closed={breakerStates['CB9'] === 'CLOSED'} label="CB9" onClick={() => onBreakerClick('CB9')} />
        <Wire x1={CB9_CX} y1={CB9_CY + 7} x2={CB9_CX} y2={LOAD_Y - 7} colour={energisedColour(en.load3)} />
        <LoadSymbol cx={CB9_CX} cy={LOAD_Y} colour={energisedColour(en.load3)} label="Load 3" />

        {/* ══════════════════════════════════════════════════════════════════
            MEASUREMENT TAGS — floating data labels
        ══════════════════════════════════════════════════════════════════ */}

        {/* Bus A voltage tag */}
        {busA.voltage_kv > 0 && (
          <MeasurementTag
            x={BUS_A_X1} y={HV_Y + 12}
            lines={[
              { label: 'V', value: `${busA.voltage_kv?.toFixed(3)} kV`, colour: voltageColour(busA.voltage_pu) },
              { label: 'I', value: `${f1.current_a?.toFixed(1)} A` },
            ]}
          />
        )}

        {/* Bus B voltage tag */}
        {busB.voltage_kv > 0 && (
          <MeasurementTag
            x={BUS_B_X2 - 85} y={HV_Y + 12}
            lines={[
              { label: 'V', value: `${busB.voltage_kv?.toFixed(3)} kV`, colour: voltageColour(busB.voltage_pu) },
              { label: 'I', value: `${f2.current_a?.toFixed(1)} A` },
            ]}
          />
        )}

        {/* TX1 measurement tag */}
        {tx1.loading_pct > 0 && (
          <MeasurementTag
            x={BUS_A_CX + 22} y={TX1_CY - 18}
            lines={[
              { label: 'Load', value: `${tx1.loading_pct?.toFixed(1)}%`, colour: loadingColour(tx1.loading_pct) },
              { label: 'P',    value: `${tx1.power_kw?.toFixed(0)} kW` },
              { label: 'Q',    value: `${tx1.power_kvar?.toFixed(0)} kvar` },
            ]}
          />
        )}

        {/* TX2 measurement tag */}
        {tx2.loading_pct > 0 && (
          <MeasurementTag
            x={BUS_B_CX + 22} y={TX2_CY - 18}
            lines={[
              { label: 'Load', value: `${tx2.loading_pct?.toFixed(1)}%`, colour: loadingColour(tx2.loading_pct) },
              { label: 'P',    value: `${tx2.power_kw?.toFixed(0)} kW` },
              { label: 'Q',    value: `${tx2.power_kvar?.toFixed(0)} kvar` },
            ]}
          />
        )}

        {/* Bus C voltage tag */}
        {busC.voltage_kv > 0 && (
          <MeasurementTag
            x={BUS_C_X1} y={LV_Y + 12}
            lines={[
              { label: 'V', value: `${busC.voltage_kv?.toFixed(4)} kV`, colour: voltageColour(busC.voltage_pu) },
            ]}
          />
        )}

        {/* Bus D voltage tag */}
        {busD.voltage_kv > 0 && (
          <MeasurementTag
            x={BUS_D_X2 - 85} y={LV_Y + 12}
            lines={[
              { label: 'V', value: `${busD.voltage_kv?.toFixed(4)} kV`, colour: voltageColour(busD.voltage_pu) },
            ]}
          />
        )}

        {/* Voltage level labels on the right margin */}
        <text x={VB_W - 8} y={HV_Y + 4} fill="#334155" fontSize={9} fontFamily="monospace" textAnchor="end">11 kV</text>
        <text x={VB_W - 8} y={LV_Y + 4} fill="#334155" fontSize={9} fontFamily="monospace" textAnchor="end">0.4 kV</text>

        {/* Dashed voltage level separator line */}
        <line x1={20} y1={315} x2={VB_W - 20} y2={315} stroke="#1e293b" strokeWidth={1} strokeDasharray="6 4" />
        <text x={24} y={311} fill="#1e2d3d" fontSize={8} fontFamily="monospace">11kV / 0.4kV boundary</text>

      </svg>
    </div>
  )
}
