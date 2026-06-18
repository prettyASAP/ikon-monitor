import { useEffect, useRef, useState } from 'react'
import * as d3 from 'd3'

const CATEGORY_COLOR = {
  'releváns':         '#3fb950',
  'felülvizsgálandó': '#e3b341',
  'zaj':              '#484f58',
}
const TIER_COLOR = {
  'tier1_specifikus': '#f85149',
  'tier2_kozepes':    '#e3b341',
  'tier3_generikus':  '#58a6ff',
}
const TIER_LABEL = {
  'tier1_specifikus': 'Tier 1',
  'tier2_kozepes':    'Tier 2',
  'tier3_generikus':  'Tier 3',
}

export default function ForceGraph({ articles = [] }) {
  const svgRef = useRef(null)
  const tooltipRef = useRef(null)
  const [nodeCount, setNodeCount] = useState({ kw: 0, art: 0, edge: 0 })

  useEffect(() => {
    if (!articles.length || !svgRef.current) return

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    const W = svgRef.current.clientWidth
    const H = svgRef.current.clientHeight

    // Build nodes and links from articles
    const kwMap = new Map()
    const artNodes = []
    const links = []

    for (const art of articles) {
      const artNode = {
        id: `art:${art.article_id}`,
        type: 'article',
        label: (art.title || '').slice(0, 40),
        fullTitle: art.title,
        score: art.score,
        category: art.category,
        url: art.url,
        source: art.source,
        r: 4 + Math.sqrt(Math.max(0, art.score || 0)) * 0.8,
      }
      artNodes.push(artNode)

      for (const kw of (art.matched_keywords || [])) {
        if (!kwMap.has(kw)) {
          kwMap.set(kw, {
            id: `kw:${kw}`,
            type: 'keyword',
            label: kw,
            tier: art.best_tier || 'tier3_generikus',
            count: 0,
            r: 0,
          })
        }
        kwMap.get(kw).count++
        links.push({ source: `kw:${kw}`, target: `art:${art.article_id}` })
      }
    }

    const kwNodes = [...kwMap.values()].map(kw => ({
      ...kw,
      r: 6 + Math.sqrt(kw.count) * 4,
    }))

    const nodes = [...kwNodes, ...artNodes]
    setNodeCount({ kw: kwNodes.length, art: artNodes.length, edge: links.length })

    // Zoom container
    const g = svg.append('g')

    svg.call(
      d3.zoom()
        .scaleExtent([0.15, 4])
        .on('zoom', e => g.attr('transform', e.transform))
    )

    // Force simulation
    const sim = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(links).id(d => d.id).distance(d => {
        const src = d.source?.type === 'keyword' ? d.source : d.target
        return 30 + (src?.count || 1) * 6
      }).strength(0.4))
      .force('charge', d3.forceManyBody().strength(d => d.type === 'keyword' ? -120 : -40))
      .force('center', d3.forceCenter(W / 2, H / 2))
      .force('collide', d3.forceCollide(d => d.r + 3))
      .alphaDecay(0.02)

    // Links
    const link = g.append('g')
      .attr('class', 'links')
      .selectAll('line')
      .data(links)
      .join('line')
      .attr('stroke', '#21262d')
      .attr('stroke-width', 1)
      .attr('stroke-opacity', 0.6)

    // Nodes
    const node = g.append('g')
      .attr('class', 'nodes')
      .selectAll('circle')
      .data(nodes)
      .join('circle')
      .attr('r', d => d.r)
      .attr('fill', d => d.type === 'keyword'
        ? TIER_COLOR[d.tier] || '#58a6ff'
        : CATEGORY_COLOR[d.category] || '#484f58')
      .attr('fill-opacity', d => d.type === 'keyword' ? 0.9 : 0.75)
      .attr('stroke', d => d.type === 'keyword' ? '#0a0e12' : 'transparent')
      .attr('stroke-width', d => d.type === 'keyword' ? 1.5 : 0)
      .style('cursor', d => d.type === 'article' ? 'pointer' : 'default')
      .call(
        d3.drag()
          .on('start', (e, d) => { if (!e.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y })
          .on('drag',  (e, d) => { d.fx = e.x; d.fy = e.y })
          .on('end',   (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null })
      )

    // Labels for keyword nodes only
    const label = g.append('g')
      .selectAll('text')
      .data(kwNodes)
      .join('text')
      .text(d => d.label)
      .attr('font-size', d => Math.min(11, 7 + d.count * 0.5) + 'px')
      .attr('fill', '#c9d1d9')
      .attr('font-family', 'JetBrains Mono, monospace')
      .attr('text-anchor', 'middle')
      .attr('dy', d => d.r + 11)
      .style('pointer-events', 'none')
      .style('user-select', 'none')

    // Tooltip
    const tooltip = d3.select(tooltipRef.current)

    node
      .on('mouseenter', (e, d) => {
        const tip = d.type === 'keyword'
          ? `<b>${d.label}</b><br/>${TIER_LABEL[d.tier] || d.tier}<br/>Cikkek: <b>${d.count}</b>`
          : `<b>${d.fullTitle || d.label}</b><br/>${d.source}<br/>Score: <b>${d.score}</b> · ${d.category}`
        tooltip.html(tip)
          .style('display', 'block')
          .style('left', (e.offsetX + 14) + 'px')
          .style('top',  (e.offsetY - 10) + 'px')

        node.attr('fill-opacity', n =>
          n === d ? 1 : (links.some(l =>
            (l.source === d || l.source.id === d.id) && (l.target === n || l.target.id === n.id) ||
            (l.target === d || l.target.id === d.id) && (l.source === n || l.source.id === n.id)
          ) ? 0.85 : 0.2)
        )
        link.attr('stroke-opacity', l =>
          (l.source === d || l.source.id === d.id || l.target === d || l.target.id === d.id) ? 1 : 0.1
        ).attr('stroke', l =>
          (l.source === d || l.source.id === d.id || l.target === d || l.target.id === d.id)
            ? '#58a6ff' : '#21262d'
        )
      })
      .on('mousemove', e => {
        tooltip
          .style('left', (e.offsetX + 14) + 'px')
          .style('top',  (e.offsetY - 10) + 'px')
      })
      .on('mouseleave', () => {
        tooltip.style('display', 'none')
        node.attr('fill-opacity', d => d.type === 'keyword' ? 0.9 : 0.75)
        link.attr('stroke-opacity', 0.6).attr('stroke', '#21262d')
      })
      .on('click', (e, d) => {
        if (d.type === 'article' && d.url) window.open(d.url, '_blank', 'noopener')
      })

    sim.on('tick', () => {
      link
        .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x).attr('y2', d => d.target.y)
      node.attr('cx', d => d.x).attr('cy', d => d.y)
      label.attr('x', d => d.x).attr('y', d => d.y)
    })

    return () => sim.stop()
  }, [articles])

  return (
    <div className="network-container">
      <svg ref={svgRef} className="network-svg" />
      <div ref={tooltipRef} className="network-tooltip" style={{ display: 'none' }} />

      <div className="network-legend">
        <div className="sidebar-section-title">Kulcsszavak</div>
        {Object.entries(TIER_COLOR).map(([tier, color]) => (
          <div key={tier} className="legend-row">
            <div className="legend-dot" style={{ background: color }} />
            {TIER_LABEL[tier]}
          </div>
        ))}
        <div className="sidebar-section-title" style={{ marginTop: 10 }}>Cikkek</div>
        {Object.entries(CATEGORY_COLOR).map(([cat, color]) => (
          <div key={cat} className="legend-row">
            <div className="legend-dot" style={{ background: color }} />
            {cat}
          </div>
        ))}
        <div style={{ marginTop: 10, color: 'var(--text-dim)', fontSize: 10 }}>
          {nodeCount.kw} kw · {nodeCount.art} cikk · {nodeCount.edge} él
        </div>
      </div>
    </div>
  )
}
