import { useEffect, useState } from 'react'
import {
  getAlerts,
  getGridActivity,
  getHotspots,
  getNetworkSummary,
  predictRisk,
} from './api'
import './App.css'


function OperationalGridMap({
  geoJson,
  hotspots,
  alerts,
  onGridClick,
}) {
  if (!geoJson) {
    return (
      <div className="map-empty-state">
        Loading Milan grid reference...
      </div>
    )
  }

  const hotspotIds = new Set(
    hotspots.map((item) => Number(item.grid_id))
  )

  const alertByGrid = new Map(
    alerts.map((item) => [
      Number(item.grid_id),
      item,
    ])
  )

  const activeIds = new Set([
    ...hotspotIds,
    ...alertByGrid.keys(),
  ])

  const selectedFeatures = geoJson.features.filter(
    (feature) =>
      activeIds.has(
        Number(feature.properties?.cellId)
      )
  )

  if (selectedFeatures.length === 0) {
    return (
      <div className="map-empty-state">
        No operational grids available for the current filters.
      </div>
    )
  }

  const allCoordinates = selectedFeatures.flatMap(
    (feature) => feature.geometry.coordinates[0]
  )

  const longitudes = allCoordinates.map(
    ([lng]) => lng
  )

  const latitudes = allCoordinates.map(
    ([, lat]) => lat
  )

  const minLng = Math.min(...longitudes)
  const maxLng = Math.max(...longitudes)
  const minLat = Math.min(...latitudes)
  const maxLat = Math.max(...latitudes)

  const width = 1000
  const height = 500
  const padding = 40

  function project([lng, lat]) {
    const x =
      padding +
      ((lng - minLng) /
        (maxLng - minLng || 1)) *
        (width - padding * 2)

    const y =
      height -
      padding -
      ((lat - minLat) /
        (maxLat - minLat || 1)) *
        (height - padding * 2)

    return `${x},${y}`
  }

  return (
    <svg
      className="operational-map"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="Milan operational grid map"
    >
      {selectedFeatures.map((feature) => {
        const gridId = Number(
          feature.properties.cellId
        )

        const alert = alertByGrid.get(gridId)

        const isHotspot =
          hotspotIds.has(gridId)

        let state = 'normal'

        if (alert?.severity === 'high') {
          state = 'high'
        } else if (
          alert ||
          isHotspot
        ) {
          state = 'attention'
        }

        const points =
          feature.geometry.coordinates[0]
            .map(project)
            .join(' ')

        return (
          <g
            key={gridId}
            className="map-grid-group"
            onClick={() =>
              onGridClick(gridId)
            }
            tabIndex="0"
            role="button"
            aria-label={`Open grid ${gridId}`}
            onKeyDown={(event) => {
              if (
                event.key === 'Enter' ||
                event.key === ' '
              ) {
                event.preventDefault()
                onGridClick(gridId)
              }
            }}
          >
            <polygon
              points={points}
              className={`map-grid map-grid-${state}`}
            />

            <title>
              {`Grid ${gridId} — ${state.toUpperCase()}`}
            </title>
          </g>
        )
      })}
    </svg>
  )
}


function App() {
  // =========================================================
  // RE1 / RE2 — NETWORK OVERVIEW STATE
  // =========================================================

  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [activePage, setActivePage] =
    useState('overview')


  // =========================================================
  // RE3 — GRID EXPLORER STATE
  // =========================================================

  const [gridId, setGridId] =
    useState('4821')

  const [gridData, setGridData] =
    useState(null)

  const [gridLoading, setGridLoading] =
    useState(false)

  const [gridError, setGridError] =
    useState('')


  // =========================================================
  // RE4 — HOTSPOTS / ALERTS STATE
  // =========================================================

  const [hotspots, setHotspots] =
    useState([])

  const [alerts, setAlerts] =
    useState([])

  const [hotspotLimit, setHotspotLimit] =
    useState(5)

  const [alertLimit, setAlertLimit] =
    useState(5)

  const [
    severityFilter,
    setSeverityFilter,
  ] = useState('')

  const [re4Loading, setRe4Loading] =
    useState(false)

  const [re4Error, setRe4Error] =
    useState('')


  // =========================================================
  // RE4 — MILAN GEOJSON STATE
  // =========================================================

  const [gridGeoJson, setGridGeoJson] =
    useState(null)

  const [geoError, setGeoError] =
    useState('')

//re5//
  const [riskForm, setRiskForm] = useState({
  avg_activity: '339.88',
  activity_growth: '0.228',
  active_hours: '168',
  peak_ratio: '2.251',
  variability: '0.394',
  internet_share: '0.848',
})

  const [riskResult, setRiskResult] = useState(null)
  const [riskLoading, setRiskLoading] = useState(false)
  const [riskError, setRiskError] = useState('')
  // =========================================================
  // RE1 / RE2 — LOAD NETWORK SUMMARY
  // =========================================================

  useEffect(() => {
    let cancelled = false

    async function loadSummary() {
      try {
        setLoading(true)
        setError('')

        const data =
          await getNetworkSummary()

        if (!cancelled) {
          setSummary(data)
        }
      } catch {
        if (!cancelled) {
          setSummary(null)

          setError(
            'Unable to load network summary. Please check the Network Operations API.'
          )
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    loadSummary()

    return () => {
      cancelled = true
    }
  }, [])


  // =========================================================
  // RE4 — LOAD GEOJSON ONCE
  // =========================================================

  useEffect(() => {
    let cancelled = false

    async function loadGridReference() {
      try {
        const response = await fetch(
          '/reference/milano-grid.geojson'
        )

        if (!response.ok) {
          throw new Error(
            'Unable to load Milan grid reference.'
          )
        }

        const data =
          await response.json()

        if (!cancelled) {
          setGridGeoJson(data)
          setGeoError('')
        }
      } catch {
        if (!cancelled) {
          setGridGeoJson(null)

          setGeoError(
            'Milan grid reference could not be loaded.'
          )
        }
      }
    }

    loadGridReference()

    return () => {
      cancelled = true
    }
  }, [])


  // =========================================================
  // RE4 — LOAD HOTSPOTS / ALERTS WHEN PAGE OR FILTER CHANGES
  // =========================================================

  useEffect(() => {
    if (activePage === 'hotspots') {
      loadOperationalIntelligence()
    }
  }, [
    activePage,
    hotspotLimit,
    alertLimit,
    severityFilter,
  ])


  // =========================================================
  // RE3 — GRID SEARCH
  // =========================================================
  function handleRiskInputChange(event) {
  const { name, value } = event.target

  setRiskForm((current) => ({
    ...current,
    [name]: value,
  }))
}

async function handleRiskSubmit(event) {
  event.preventDefault()

  setRiskLoading(true)
  setRiskError('')
  setRiskResult(null)

  try {
    const payload = {
      avg_activity: Number(riskForm.avg_activity),
      activity_growth: Number(riskForm.activity_growth),
      active_hours: Number(riskForm.active_hours),
      peak_ratio: Number(riskForm.peak_ratio),
      variability: Number(riskForm.variability),
      internet_share: Number(riskForm.internet_share),
    }

    const data = await predictRisk(payload)
    setRiskResult(data)
  } catch (err) {
    setRiskError(
      err.message ||
        'Unable to generate a risk prediction from the API.'
    )
  } finally {
    setRiskLoading(false)
  }
}
  async function handleGridSearch(event) {
    event.preventDefault()

    const normalizedGridId =
      gridId.trim()

    if (!normalizedGridId) {
      setGridError(
        'Enter a grid ID to continue.'
      )

      setGridData(null)

      return
    }

    try {
      setGridLoading(true)
      setGridError('')
      setGridData(null)

      const data =
        await getGridActivity(
          normalizedGridId
        )

      setGridData(data)
    } catch (err) {
      if (err.status === 404) {
        setGridError(
          `Grid ${normalizedGridId} was not found.`
        )
      } else {
        setGridError(
          'Unable to load grid activity. Please check the Network Operations API.'
        )
      }
    } finally {
      setGridLoading(false)
    }
  }


  // =========================================================
  // RE4 — LOAD OPERATIONAL INTELLIGENCE
  // =========================================================

  async function loadOperationalIntelligence() {
    try {
      setRe4Loading(true)
      setRe4Error('')

      const [
        hotspotResponse,
        alertResponse,
      ] = await Promise.all([
        getHotspots(hotspotLimit),
        getAlerts(
          alertLimit,
          severityFilter
        ),
      ])

      setHotspots(
        hotspotResponse.hotspots ?? []
      )

      setAlerts(
        alertResponse.alerts ?? []
      )
    } catch {
      setHotspots([])
      setAlerts([])

      setRe4Error(
        'Unable to load hotspot and alert intelligence from the API.'
      )
    } finally {
      setRe4Loading(false)
    }
  }


  // =========================================================
  // RE4 — OPEN GRID FROM MAP
  // =========================================================

  function openGridFromMap(
    selectedGridId
  ) {
    setGridId(
      String(selectedGridId)
    )

    setActivePage('grid')

    setGridError('')
    setGridData(null)
  }


  // =========================================================
  // FORMATTERS
  // =========================================================

  function formatNumber(
    value,
    maximumFractionDigits = 2
  ) {
    if (
      value === null ||
      value === undefined ||
      Number.isNaN(Number(value))
    ) {
      return '—'
    }

    return Number(value).toLocaleString(
      undefined,
      {
        maximumFractionDigits,
      }
    )
  }


  function formatPeakHour(hour) {
    if (
      hour === null ||
      hour === undefined
    ) {
      return '—'
    }

    return `${String(hour).padStart(
      2,
      '0'
    )}:00`
  }


  // =========================================================
  // APP
  // =========================================================

  return (
    <div className="app-shell">

      {/* =====================================================
          SIDEBAR
      ====================================================== */}

      <aside className="sidebar">

        <div className="brand">

          <div className="brand-mark">
            N
          </div>

          <div className="brand-copy">
            <h1>NetworkOps</h1>

            <p>
              Operations Intelligence
            </p>
          </div>

        </div>


        <nav className="sidebar-nav">

  <button
    type="button"
    className={`nav-item ${
      activePage === 'overview' ? 'active' : ''
    }`}
    onClick={() => setActivePage('overview')}
  >
    Overview
  </button>

  <button
    type="button"
    className={`nav-item ${
      activePage === 'grid' ? 'active' : ''
    }`}
    onClick={() => setActivePage('grid')}
  >
    Grid Explorer
  </button>

  <button
    type="button"
    className={`nav-item ${
      activePage === 'hotspots' ? 'active' : ''
    }`}
    onClick={() => setActivePage('hotspots')}
  >
    Hotspots & Alerts
  </button>

  <button
    type="button"
    className={`nav-item ${
      activePage === 'predictive' ? 'active' : ''
    }`}

    onClick={() => setActivePage('predictive')}
  >
    Predictive Risk
  </button>

</nav>


        <div className="sidebar-footer">

          <div
            className={`api-status ${
              loading
                ? 'api-loading'
                : error
                  ? 'api-error'
                  : 'api-connected'
            }`}
          >

            <span className="status-dot"></span>

            <span>
              {loading
                ? 'Checking API'
                : error
                  ? 'API unavailable'
                  : 'API connected'}
            </span>

          </div>

        </div>

      </aside>


      {/* =====================================================
          MAIN CONTENT
      ====================================================== */}

      <main className="main-content">


        {/* ===================================================
            RE1 / RE2 — OVERVIEW
        ==================================================== */}

        {activePage === 'overview' && (
          <>

            <header className="page-header">

              <div>

                <p className="eyebrow">
                  NETWORK OPERATIONS CENTER
                </p>

                <h2>
                  Network Overview
                </h2>

                <p className="page-description">
                  Current aggregated network activity and operational coverage.
                </p>

              </div>


              <div className="environment-badge">
                Operations View
              </div>

            </header>


            {loading && (

              <section className="state-panel">

                <div className="loader"></div>

                <div>

                  <h3>
                    Loading network summary
                  </h3>

                  <p>
                    Retrieving current operational metrics...
                  </p>

                </div>

              </section>

            )}


            {!loading && error && (

              <section className="state-panel error-panel">

                <div className="error-icon">
                  !
                </div>

                <div>

                  <h3>
                    Network summary unavailable
                  </h3>

                  <p>
                    {error}
                  </p>

                </div>

              </section>

            )}


            {!loading &&
              !error &&
              summary && (
                <>

                  <section className="reporting-strip">

                    <div>

                      <span className="reporting-label">
                        Reporting As Of
                      </span>

                      <strong>
                        {summary.as_of}
                      </strong>

                    </div>

                    <p>
                      Metrics below reflect the API reporting timestamp.
                    </p>

                  </section>


                  <section className="metric-grid">

                    <article className="metric-card">

                      <div className="metric-card-header">

                        <span className="metric-label">
                          TOTAL ACTIVITY
                        </span>

                        <span className="metric-index">
                          01
                        </span>

                      </div>

                      <strong className="metric-value">
                        {formatNumber(
                          summary.total_activity,
                          0
                        )}
                      </strong>

                      <p className="metric-description">
                        Aggregated network activity indicator.
                      </p>

                    </article>


                    <article className="metric-card">

                      <div className="metric-card-header">

                        <span className="metric-label">
                          ACTIVE GRIDS
                        </span>

                        <span className="metric-index">
                          02
                        </span>

                      </div>

                      <strong className="metric-value">
                        {formatNumber(
                          summary.active_grids,
                          0
                        )}
                      </strong>

                      <p className="metric-description">
                        Grid cells contributing activity at the reporting point.
                      </p>

                    </article>


                    <article className="metric-card">

                      <div className="metric-card-header">

                        <span className="metric-label">
                          PEAK HOUR
                        </span>

                        <span className="metric-index">
                          03
                        </span>

                      </div>

                      <strong className="metric-value">
                        {formatPeakHour(
                          summary.peak_hour
                        )}
                      </strong>

                      <p className="metric-description">
                        Hour with the highest aggregated network activity.
                      </p>

                    </article>


                    <article className="metric-card">

                      <div className="metric-card-header">

                        <span className="metric-label">
                          TOP GRID
                        </span>

                        <span className="metric-index">
                          04
                        </span>

                      </div>

                      <strong className="metric-value">
                        #{summary.top_grid}
                      </strong>

                      <p className="metric-description">
                        Grid with the highest aggregated activity.
                      </p>

                    </article>

                  </section>

                </>
              )}

          </>
        )}


        {/* ===================================================
            RE3 — GRID EXPLORER
        ==================================================== */}

        {activePage === 'grid' && (
          <>

            <header className="page-header">

              <div>

                <p className="eyebrow">
                  NETWORK OPERATIONS CENTER
                </p>

                <h2>
                  Grid Explorer
                </h2>

                <p className="page-description">
                  Inspect hourly SMS, call, internet, and total activity for an individual grid.
                </p>

              </div>


              <div className="environment-badge">
                Grid Investigation
              </div>

            </header>


            <section className="grid-search-panel">

              <form
                className="grid-search-form"
                onSubmit={
                  handleGridSearch
                }
                noValidate
              >

                <div className="grid-input-group">

                  <label htmlFor="grid-id">
                    GRID ID
                  </label>

                  <input
                    id="grid-id"
                    type="number"
                    min="1"
                    value={gridId}
                    onChange={(event) =>
                      setGridId(
                        event.target.value
                      )
                    }
                    placeholder="e.g. 4821"
                  />

                </div>


                <button
                  className="primary-button"
                  type="submit"
                  disabled={gridLoading}
                >
                  {gridLoading
                    ? 'Loading...'
                    : 'Inspect Grid'}
                </button>

              </form>

            </section>


            {gridLoading && (

              <section className="state-panel">

                <div className="loader"></div>

                <div>

                  <h3>
                    Loading grid activity
                  </h3>

                  <p>
                    Retrieving hourly activity for grid {gridId}...
                  </p>

                </div>

              </section>

            )}


            {!gridLoading &&
              gridError && (

                <section className="state-panel error-panel">

                  <div className="error-icon">
                    !
                  </div>

                  <div>

                    <h3>
                      Grid activity unavailable
                    </h3>

                    <p>
                      {gridError}
                    </p>

                  </div>

                </section>

              )}


            {!gridLoading &&
              !gridError &&
              gridData && (
                <>

                  <section className="grid-result-header">

                    <div>

                      <p className="section-label">
                        GRID ACTIVITY
                      </p>

                      <h3>
                        Grid #{gridData.grid_id}
                      </h3>

                    </div>

                    <span className="point-count-badge">
                      {gridData.point_count} hourly points
                    </span>

                  </section>


                  <section className="grid-meta-strip">

                    <div>

                      <span>
                        REPORTING AS OF
                      </span>

                      <strong>
                        {gridData.as_of}
                      </strong>

                    </div>


                    <div>

                      <span>
                        WINDOW START
                      </span>

                      <strong>
                        {gridData.window_start}
                      </strong>

                    </div>


                    <div>

                      <span>
                        WINDOW END
                      </span>

                      <strong>
                        {gridData.window_end}
                      </strong>

                    </div>


                    <div>

                      <span>
                        POINTS
                      </span>

                      <strong>
                        {gridData.point_count}
                      </strong>

                    </div>

                  </section>


                  <section className="series-legend">

                    <span>
                      <span className="series-marker sms-marker"></span>
                      SMS Activity
                    </span>

                    <span>
                      <span className="series-marker call-marker"></span>
                      Call Activity
                    </span>

                    <span>
                      <span className="series-marker internet-marker"></span>
                      Internet Activity
                    </span>

                    <span>
                      <span className="series-marker total-marker"></span>
                      Total Activity
                    </span>

                  </section>


                  <section className="grid-table-panel">

                    <div className="table-heading">

                      <div>

                        <p className="section-label">
                          HOURLY SERIES
                        </p>

                        <h3>
                          Activity timeline
                        </h3>

                      </div>

                      <span>
                        {gridData.series.length} rows
                      </span>

                    </div>


                    <div className="table-scroll">

                      <table className="activity-table">

                        <thead>

                          <tr>
                            <th>Time</th>
                            <th>SMS Activity</th>
                            <th>Call Activity</th>
                            <th>Internet Activity</th>
                            <th>Total Activity</th>
                          </tr>

                        </thead>


                        <tbody>

                          {gridData.series.map(
                            (point) => (

                              <tr
                                key={point.ts}
                              >

                                <td className="timestamp-cell">

                                  <strong>
                                    {String(
                                      point.hour
                                    ).padStart(
                                      2,
                                      '0'
                                    )}
                                    :00
                                  </strong>

                                  <span>
                                    {point.ts}
                                  </span>

                                </td>


                                <td className="sms-value">
                                  {formatNumber(
                                    point.sms_activity
                                  )}
                                </td>


                                <td className="call-value">
                                  {formatNumber(
                                    point.call_activity
                                  )}
                                </td>


                                <td className="internet-value">
                                  {formatNumber(
                                    point.internet_activity
                                  )}
                                </td>


                                <td className="total-value">
                                  {formatNumber(
                                    point.total_activity
                                  )}
                                </td>

                              </tr>

                            )
                          )}

                        </tbody>

                      </table>

                    </div>

                  </section>

                </>
              )}

          </>
        )}


        {/* ===================================================
            RE4 — HOTSPOTS & ALERTS
        ==================================================== */}

        {activePage === 'hotspots' && (
          <>

            <header className="page-header">

              <div>

                <p className="eyebrow">
                  NETWORK OPERATIONS CENTER
                </p>

                <h2>
                  Hotspots & Alerts
                </h2>

                <p className="page-description">
                  Ranked activity hotspots and rule-based operational alerts.
                </p>

              </div>


              <div className="environment-badge">
                Operational Prioritization
              </div>

            </header>


            <section className="re4-controls">

              <div className="control-group">

                <label htmlFor="hotspot-limit">
                  Hotspot limit
                </label>

                <select
                  id="hotspot-limit"
                  value={hotspotLimit}
                  onChange={(event) =>
                    setHotspotLimit(
                      Number(
                        event.target.value
                      )
                    )
                  }
                >
                  <option value={5}>
                    Top 5
                  </option>

                  <option value={10}>
                    Top 10
                  </option>

                  <option value={20}>
                    Top 20
                  </option>
                </select>

              </div>


              <div className="control-group">

                <label htmlFor="alert-limit">
                  Alert limit
                </label>

                <select
                  id="alert-limit"
                  value={alertLimit}
                  onChange={(event) =>
                    setAlertLimit(
                      Number(
                        event.target.value
                      )
                    )
                  }
                >
                  <option value={5}>
                    5 alerts
                  </option>

                  <option value={10}>
                    10 alerts
                  </option>

                  <option value={20}>
                    20 alerts
                  </option>
                </select>

              </div>


              <div className="control-group">

                <label htmlFor="severity-filter">
                  Severity
                </label>

                <select
                  id="severity-filter"
                  value={severityFilter}
                  onChange={(event) =>
                    setSeverityFilter(
                      event.target.value
                    )
                  }
                >
                  <option value="">
                    All severities
                  </option>

                  <option value="high">
                    High
                  </option>

                  <option value="medium">
                    Medium
                  </option>

                  <option value="low">
                    Low
                  </option>
                </select>

              </div>

            </section>


            {re4Loading && (

              <section className="state-panel">

                <div className="loader"></div>

                <div>

                  <h3>
                    Loading operational intelligence
                  </h3>

                  <p>
                    Retrieving hotspots and alerts...
                  </p>

                </div>

              </section>

            )}


            {!re4Loading &&
              re4Error && (

                <section className="state-panel error-panel">

                  <div className="error-icon">
                    !
                  </div>

                  <div>

                    <h3>
                      Operational intelligence unavailable
                    </h3>

                    <p>
                      {re4Error}
                    </p>

                  </div>

                </section>

              )}


            {!re4Loading &&
              !re4Error && (
                <>

                  <section className="re4-grid">

                    {/* HOTSPOTS */}

                    <div className="operational-panel">

                      <div className="table-heading">

                        <div>

                          <p className="section-label">
                            HOTSPOTS
                          </p>

                          <h3>
                            Highest activity grids
                          </h3>

                        </div>

                        <span>
                          {hotspots.length} shown
                        </span>

                      </div>


                      <div className="table-scroll">

                        <table className="activity-table">

                          <thead>

                            <tr>
                              <th>Rank</th>
                              <th>Grid</th>
                              <th>Timestamp</th>
                              <th>Activity</th>
                              <th>Status</th>
                            </tr>

                          </thead>


                          <tbody>

                            {hotspots.map(
                              (
                                item,
                                index
                              ) => (

                                <tr
                                  key={`${item.grid_id}-${item.ts}`}
                                >

                                  <td>
                                    #{index + 1}
                                  </td>

                                  <td>
                                    #{item.grid_id}
                                  </td>

                                  <td>
                                    {item.ts}
                                  </td>

                                  <td>
                                    {formatNumber(
                                      item.total_activity
                                    )}
                                  </td>

                                  <td>

                                    <span className="status-pill status-attention">
                                      ATTENTION
                                    </span>

                                  </td>

                                </tr>

                              )
                            )}

                          </tbody>

                        </table>

                      </div>

                    </div>


                    {/* ALERTS */}

                    <div className="operational-panel">

                      <div className="table-heading">

                        <div>

                          <p className="section-label">
                            ALERTS
                          </p>

                          <h3>
                            Current rule-based alerts
                          </h3>

                        </div>

                        <span>
                          {alerts.length} shown
                        </span>

                      </div>


                      <div className="table-scroll">

                        <table className="activity-table">

                          <thead>

                            <tr>
                              <th>Grid</th>
                              <th>Timestamp</th>
                              <th>Activity</th>
                              <th>Baseline</th>
                              <th>Severity</th>
                            </tr>

                          </thead>


                          <tbody>

                            {alerts.map(
                              (item) => (

                                <tr
                                  key={`${item.grid_id}-${item.ts}`}
                                >

                                  <td>
                                    #{item.grid_id}
                                  </td>

                                  <td>
                                    {item.ts}
                                  </td>

                                  <td>
                                    {formatNumber(
                                      item.total_activity
                                    )}
                                  </td>

                                  <td>
                                    {formatNumber(
                                      item.baseline_activity
                                    )}
                                  </td>

                                  <td>

                                    <span
                                      className={`status-pill ${
                                        item.severity ===
                                        'high'
                                          ? 'status-high'
                                          : 'status-attention'
                                      }`}
                                    >
                                      {item.severity?.toUpperCase()}
                                    </span>

                                  </td>

                                </tr>

                              )
                            )}

                          </tbody>

                        </table>

                      </div>

                    </div>

                  </section>


                  {/* =========================================
                      RE4 MILAN MAP
                  ========================================== */}

                  <section className="map-panel">

                    <div className="table-heading">

                      <div>

                        <p className="section-label">
                          MILAN GRID MAP
                        </p>

                        <h3>
                          Operational attention areas
                        </h3>

                      </div>

                      <span>
                        {hotspots.length +
                          alerts.length}{' '}
                        API signals
                      </span>

                    </div>


                    <div className="map-legend">

                      <span className="map-legend-item">

                        <span className="map-swatch map-swatch-normal"></span>

                        NORMAL

                      </span>


                      <span className="map-legend-item">

                        <span className="map-swatch map-swatch-attention"></span>

                        ATTENTION

                      </span>


                      <span className="map-legend-item">

                        <span className="map-swatch map-swatch-high"></span>

                        HIGH

                      </span>

                    </div>


                    {geoError ? (

                      <div className="map-empty-state">
                        {geoError}
                      </div>

                    ) : (

                      <OperationalGridMap
                        geoJson={
                          gridGeoJson
                        }
                        hotspots={
                          hotspots
                        }
                        alerts={
                          alerts
                        }
                        onGridClick={
                          openGridFromMap
                        }
                      />

                    )}


                    <p className="map-footnote">
                      Showing only grids returned by the current hotspot and alert queries. Select a cell to inspect it in Grid Explorer.
                    </p>

                  </section>

                </>
              )}

          </>
        )}


        {/* ===================================================
            RE5 — PREDICTIVE RISK PLACEHOLDER
        ==================================================== */}

        {activePage === 'risk' && (
          <>

            <header className="page-header">

              <div>

                <p className="eyebrow">
                  NETWORK OPERATIONS CENTER
                </p>

                <h2>
                  Predictive Risk
                </h2>

                <p className="page-description">
                  Model-based network attention signals.
                </p>

              </div>


              <div className="environment-badge">
                Predictive Intelligence
              </div>

            </header>


            <section className="state-panel">

              <div>

                <h3>
                  Predictive risk interface
                </h3>

                <p>
                  Prediction controls and model output will be implemented in RE5.
                </p>

              </div>

            </section>

          </>
        )}
        {activePage === 'predictive' && (
  <section className="page-section">
    <div className="page-header">
      <div>
        <p className="eyebrow">PREDICTIVE INTELLIGENCE</p>
        <h1>Predictive Risk</h1>
        <p className="page-subtitle">
          Evaluate operational risk from engineered network features.
        </p>
      </div>
    </div>

    <div className="risk-layout">
      <form
        className="risk-form-panel"
        onSubmit={handleRiskSubmit}
      >
        <div className="panel-heading">
          <div>
            <p className="panel-eyebrow">
              MODEL INPUT
            </p>
            <h2>Network feature inputs</h2>
          </div>
        </div>

        <div className="risk-form-grid">
          <label>
            <span>Average Activity</span>
            <input
              type="number"
              step="any"
              name="avg_activity"
              value={riskForm.avg_activity}
              onChange={handleRiskInputChange}
              required
            />
          </label>

          <label>
            <span>Activity Growth</span>
            <input
              type="number"
              step="any"
              name="activity_growth"
              value={riskForm.activity_growth}
              onChange={handleRiskInputChange}
              required
            />
          </label>

          <label>
            <span>Active Hours</span>
            <input
              type="number"
              step="1"
              name="active_hours"
              value={riskForm.active_hours}
              onChange={handleRiskInputChange}
              required
            />
          </label>

          <label>
            <span>Peak Ratio</span>
            <input
              type="number"
              step="any"
              name="peak_ratio"
              value={riskForm.peak_ratio}
              onChange={handleRiskInputChange}
              required
            />
          </label>

          <label>
            <span>Variability</span>
            <input
              type="number"
              step="any"
              name="variability"
              value={riskForm.variability}
              onChange={handleRiskInputChange}
              required
            />
          </label>

          <label>
            <span>Internet Share</span>
            <input
              type="number"
              step="any"
              name="internet_share"
              value={riskForm.internet_share}
              onChange={handleRiskInputChange}
              required
            />
          </label>
        </div>

        <button
          type="submit"
          className="primary-button"
          disabled={riskLoading}
        >
          {riskLoading
            ? 'Evaluating...'
            : 'Evaluate Risk'}
        </button>

        {riskError && (
          <div className="error-banner">
            {riskError}
          </div>
        )}
      </form>

      <div className="risk-result-panel">
        <div className="panel-heading">
          <div>
            <p className="panel-eyebrow">
              MODEL OUTPUT
            </p>
            <h2>Risk assessment</h2>
          </div>
        </div>

        {!riskResult && !riskLoading && (
          <div className="risk-empty-state">
            Submit the network features to generate
            a predictive risk assessment.
          </div>
        )}

        {riskLoading && (
          <div className="risk-empty-state">
            Evaluating model response...
          </div>
        )}

        {riskResult && (
          <>
            <div className="risk-score-block">
              <span className="risk-score-label">
                Risk Score
              </span>

              <strong className="risk-score-value">
                {Number(riskResult.risk_score).toFixed(2)}
              </strong>

              <span
                className={`risk-level-badge risk-level-${riskResult.risk_level}`}
              >
                {riskResult.risk_level.toUpperCase()}
              </span>
            </div>

            <div className="risk-meta">
              <span>Model Version</span>
              <strong>
                {riskResult.model_version}
              </strong>
            </div>

            <div className="risk-narrative">
              <p className="panel-eyebrow">
                MODEL NOTE
              </p>

              <p>
                {riskResult.explanation_note}
              </p>
            </div>

            <button
              type="button"
              className="secondary-button"
              disabled
            >
              Explain with AI
            </button>

            <p className="placeholder-note">
              AI-assisted explanation is reserved for a later phase.
            </p>
          </>
        )}
      </div>
    </div>
  </section>
)}

      </main>

    </div>
  )
}

export default App
