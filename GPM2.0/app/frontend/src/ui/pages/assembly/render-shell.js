export function renderAssemblyPage(state, deps) {
  const addCtgImportProgressModal = deps.renderAddCtgImportProgressModal(state);
  const batchDeleteProgressModal = deps.renderBatchDeleteProgressModal(state);
  const confirmModal = deps.renderAssemblyConfirmModal(state);
  const finalPathExportModal = deps.renderFinalPathExportModal(state);
  const activeTabContent = renderActiveAssemblyTab(state, deps);

  return `
    <section class="page">
      <section class="assembly-tabs">
        <div class="tab-body">${activeTabContent}</div>
      </section>
      <div id="assembly-context-menu" class="context-menu is-hidden"></div>
      ${confirmModal}
      ${addCtgImportProgressModal}
      ${batchDeleteProgressModal}
      ${finalPathExportModal}
    </section>
  `;
}

function renderActiveAssemblyTab(state, deps) {
  const assembly = state.assembly;
  const session = state.session;
  const i18n = deps.getAssemblyI18n(state);
  if (assembly.activeTab === "assembly") {
    return deps.renderAssemblyMainTab(state);
  }

  if (assembly.activeTab === "contig-list") {
    const sortedItems = deps.getSortedContigListItems(assembly.chrCtgs);
    const rows = sortedItems.length
      ? sortedItems
          .map(
            (ctg) => `<tr>
              <td>${ctg.assemblyCtgId}</td>
              <td>${deps.escapeHtml(ctg.name)}</td>
              <td>${deps.escapeHtml(ctg.assignedChrName || i18n.unplaced)}</td>
              <td>${ctg.memberCount}</td>
              <td>${deps.formatBp(ctg.totalLength)}</td>
              <td>${deps.formatAnchorStart(ctg.anchorStart)}</td>
              <td><button class="button ghost tiny" data-assembly-ctg-id="${ctg.assemblyCtgId}" data-track-focus-mode="center">${i18n.jumpToContig}</button></td>
            </tr>`,
          )
          .join("")
      : `<tr><td colspan="7" class="muted">${i18n.noContigsInChr}</td></tr>`;
    return `
      <article class="card assembly-tabular-card">
        <h4>${i18n.contigListTitle}</h4>
        <p class="muted">${i18n.contigListHint}</p>
        <div class="table-wrap">
          <table class="records-table assembly-tab-table">
            <thead>
              <tr>
                <th>contig ID</th>
                <th>${i18n.sequenceNameCol}</th>
                <th>${i18n.chromosomeCol}</th>
                <th>${i18n.memberCountCol}</th>
                <th>${i18n.totalLengthCol}</th>
                <th>${i18n.anchorStartCol}</th>
                <th>${i18n.jumpCol}</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </article>
    `;
  }

  if (assembly.activeTab === "stats") {
    const stats = deps.buildAssemblyStats(assembly, i18n);
    const rows = stats
      .map(
        (item) => `<tr><td>${deps.escapeHtml(item.label)}</td><td>${deps.escapeHtml(item.value)}</td></tr>`,
      )
      .join("");
    return `
      <article class="card assembly-tabular-card">
        <h4>${i18n.statsTitle}</h4>
        <table class="records-table assembly-tab-table">
          <tbody>${rows}</tbody>
        </table>
      </article>
    `;
  }

  if (assembly.activeTab === "check-new-sequences") {
    const newSequences = deps.getNewSequencesState(assembly);
    const rows = newSequences.items.length
      ? newSequences.items
          .map(
            (item) => `<tr>
              <td>${item.assemblySeqId}</td>
              <td>${deps.escapeHtml(item.datasetName || "-")}</td>
              <td>${deps.escapeHtml(item.seqName || "-")}</td>
              <td>${deps.formatBp(item.seqLength)}</td>
              <td>${item.hidden ? i18n.hidden : i18n.visible}</td>
              <td>${deps.renderNewSequenceRowActions(item, state)}</td>
            </tr>`,
          )
          .join("")
      : `<tr><td colspan="6" class="muted">${
          newSequences.loading
            ? i18n.loadingNewSequences
            : newSequences.error
              ? deps.escapeHtml(newSequences.error)
              : i18n.noNewSequences
        }</td></tr>`;
    return `
      <article class="card assembly-tabular-card">
        <h4>${i18n.newSequencesTitle}</h4>
        <p class="muted">${i18n.newSequencesHint}</p>
        <div class="table-wrap">
          <table class="records-table assembly-tab-table">
            <thead>
              <tr>
                <th>${i18n.sequenceIdCol}</th>
                <th>${i18n.datasetCol}</th>
                <th>${i18n.sequenceNameCol}</th>
                <th>${i18n.lengthCol}</th>
                <th>${i18n.statusCol}</th>
                <th>${i18n.actionsCol}</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </article>
    `;
  }

  return `
    <article class="card">
      <h4>${i18n.aboutTitle}</h4>
      <table class="records-table">
        <tbody>
          <tr><td>${i18n.projectLabel}</td><td>${deps.escapeHtml(session.projectName || "-")}</td></tr>
          <tr><td>${i18n.projectIdLabel}</td><td>${session.projectId || "-"}</td></tr>
          <tr><td>${i18n.workspaceLabel}</td><td><code>${deps.escapeHtml(session.workspacePath || "-")}</code></td></tr>
          <tr><td>${i18n.currentChrLabel}</td><td>${deps.escapeHtml(assembly.selectedChrName || "-")}</td></tr>
          <tr><td>${i18n.currentCtgLabel}</td><td>${deps.escapeHtml(assembly.ctgDetail?.name || "-")}</td></tr>
        </tbody>
      </table>
    </article>
  `;
}
