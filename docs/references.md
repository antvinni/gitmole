# References

The research, tools and standards gitmole's rules are built on; back to [the README](https://github.com/antvinni/gitmole#readme).
Each entry names what in gitmole it informs. A finding whose rule rests on a paper carries the short
citation in its `rule.ref`, so a reader checking the JSON sees it where the number is. Entries marked
*not built* informed a roadmap item that has not shipped.

## Research

- Ajienka and Capiluppi, "Understanding the interplay between the logical and structural coupling of software classes," *JSS* 134, 2017. [link](https://www.sciencedirect.com/science/article/abs/pii/S016412121730184X): the `hidden_coupling` finding.
- Avelino, Passos, Hora and Valente, "A Novel Approach for Estimating Truck Factors," *ICPC* 2016. [arXiv:1604.06766](https://arxiv.org/pdf/1604.06766): `maat.doa`, the `truck_factor` and `authors_gone` findings.
- Becker et al., "Bus Factor Explorer," *ASE* 2023 tool paper. [arXiv:2403.08038](https://arxiv.org/pdf/2403.08038): the five-month knowledge decay in `maat.doa` and the decayed truck factor.
- Bird, Nagappan, Murphy, Gall and Devanbu, "Don't Touch My Code!," *FSE* 2011. [PDF](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/bird2011dtm.pdf): the `minor` column in `maat-authors.csv`, the watch reason and the `minor_contributors` finding.
- Borg, Hagatulah, Tornhill and Söderberg, "Code for Machines, Not Just Humans," 2026. [arXiv:2601.02200](https://arxiv.org/html/2601.02200): why structure metrics earned the optional `structure.py` step.
- Boucher and Anderson, "Trojan Source: Invisible Vulnerabilities," *USENIX Security* 2023: the `trojan_source` check in `hygiene.py`.
- Eyolfson, Tan and Lam, "Correlations between bugginess and time-based commit characteristics," *EMSE* 19, 2014. [PDF](https://www.cs.purdue.edu/homes/lintan/publications/commitTime-emse14.pdf): `maat.latenight` and the midnight-to-4-am watch reason, never a rank.
- Fu and Menzies, "Revisiting Unsupervised Learning for Defect Prediction," *FSE* 2017. [arXiv:1703.00132](https://arxiv.org/pdf/1703.00132): why the Kamei factors on `--risk` stay reasons and never a score.
- Gall, Hajek and Jazayeri, "Detection of logical coupling based on product release history," *ICSM* 1998: change coupling, the `tight_coupling` finding.
- Hassan, "Predicting Faults Using the Complexity of Code Changes," *ICSE* 2009. [PDF](https://sailresearch.github.io/sail-website/data/pdfs/ICSE2009_PredictingFaultsUsingTheComplexityOfCodeChanges.pdf): `maat.entropy`, the backtest variant and the `changed in N different months` reason.
- Herzig and Zeller, "The Impact of Tangled Code Changes," *MSR* 2013. [IEEE](https://ieeexplore.ieee.org/document/6624018/): oversized fixes out of the fix pool (`maat.oversized`) and the `tangled_commits` finding.
- Huang, Xia and Lo, "Revisiting supervised and unsupervised models for effort-aware just-in-time defect prediction," *EMSE* 24, 2018. [PDF](https://xin-xia.github.io/publication/emse182.pdf): the caveat on effort-aware rankings behind `--risk`.
- Kamei et al., "A Large-Scale Empirical Study of Just-in-Time Quality Assurance," *TSE* 39(6), 2013. [PDF](https://posl.ait.kyushu-u.ac.jp/~kamei/publications/Kamei_TSE2013.pdf): `watch.change_factors`, the change reasons on `--risk`.
- Keshavarz and Nagappan, "ApacheJIT: A Large Dataset for Just-In-Time Defect Prediction," *MSR* 2022. [arXiv:2203.00101](https://ar5iv.labs.arxiv.org/html/2203.00101): the label shape `evaluate --labels` reads.
- Lanza and Marinescu, *Object-Oriented Metrics in Practice*, Springer 2006: the brain method, the `brain_methods` finding.
- Lavazza, Abualhaija, Morasca and Tosi, "An empirical evaluation of the 'Cognitive Complexity' measure as a predictor of code understandability," *JSS* 197, 2023. [ACM](https://dl.acm.org/doi/10.1016/j.jss.2022.111561): why cognitive complexity sits beside nesting in `structure.py` rather than replacing CCN.
- Mahbub, Shuvo and Rahman, "Defectors: A Large, Diverse Python Dataset for Defect Prediction," *MSR* 2023. [arXiv:2303.04738](https://www.arxiv.org/pdf/2303.04738): dropping oversized fixes; the file-level label shape `evaluate --labels` reads.
- Maldonado and Shihab, "Detecting and quantifying different types of self-admitted technical debt," *MTD* 2015. [PDF](http://users.encs.concordia.ca/~eshihab/pubs/Maldonado_MTD2015.pdf): the TODO, FIXME, XXX and HACK markers in `structure.py` and the `debt_in_hotspots` finding.
- Miranda et al., "Test Co-Evolution in Software Projects," *JSEP* 2025. [link](https://onlinelibrary.wiley.com/doi/full/10.1002/smr.70035): `maat.test_cochange` and the `no test changed` reason.
- Muñoz Barón, Wyrich and Wagner, "An Empirical Validation of Cognitive Complexity as a Measure of Source Code Understandability," *ESEM* 2020. [arXiv:2007.12520](https://arxiv.org/abs/2007.12520): cognitive complexity in `structure.py`.
- Pecorelli, Palomba and De Lucia, "The Relation of Test-Related Factors to Software Quality," *EMSE* 2021. [PDF](https://fpalomba.github.io/pdf/Journals/J35.pdf): why test co-change, not assertion density.
- Romano, Vendome, Scanniello and Poshyvanyk, "A Multi-Study Investigation into Dead Code," *TSE* 46(1), 2020. [PDF](https://www.cs.wm.edu/~denys/pubs/TSE'18-DeadCode.pdf): the `unreferenced_files` finding says "possibly unreferenced", never "dead".
- Rosa et al., "Evaluating SZZ Implementations Through a Developer-informed Oracle," *ICSE* 2021, extended *JSS* 2023. [arXiv:2102.03300](https://arxiv.org/pdf/2102.03300): R-SZZ in `szz.py` and `evaluate --szz`.
- Tornhill and Borg, "Code Red: The Business Impact of Code Quality," *TechDebt* 2022. [arXiv:2203.04374](https://arxiv.org/abs/2203.04374): why code health is worth measuring at all.
- Wang et al., "WIA-SZZ: Work Item Aware SZZ," 2024. [arXiv:2411.12740](https://arxiv.org/abs/2411.12740): the insert-only blind spot `szz.py` states and does not close.
- Yang et al., "Effort-aware just-in-time defect prediction: simple unsupervised models could be better than supervised models," *FSE* 2016. [ACM](https://dl.acm.org/doi/10.1145/2950290.2950353): the Kamei factors on `--risk`.
- Zimmermann, Weißgerber, Diehl and Zeller, "Mining Version Histories to Guide Software Changes," *TSE* 31(6), 2005. [PDF](https://thomas-zimmermann.com/publications/files/zimmermann-tse-2005.pdf): `coupling_gaps` on `--risk` and the `--hook` summary.
- "PR-SZZ: How pull requests can support the tracing of defects in software repositories," 2022. [arXiv:2206.09967](https://arxiv.org/pdf/2206.09967): crediting `Co-authored-by` trailers in `maat.py` and `blame.py`.
- "Knowledge Islands: Visualizing Developers Knowledge Concentration," *SBES* 2024. [arXiv:2408.08733](https://arxiv.org/html/2408.08733v1): recency beside authorship, behind the decayed truck factor.
- "Self-Admitted Technical Debt in methods: a large-scale study," 2024. [arXiv:2411.13777](https://arxiv.org/html/2411.13777v2): the evidence behind `debt_in_hotspots`.
- "Revisiting the Identification of the Co-evolution of Production and Test Code," *TOSEM* 2023. [ACM](https://dl.acm.org/doi/10.1145/3607183): `maat.test_cochange`.
- "The Distribution of Commit Sizes in Open Source," 2014. [arXiv:1408.4974](https://arxiv.org/pdf/1408.4974): the repository's own 99th percentile in `maat.sweeping` and `maat.oversized`.
- "Critical Considerations on Effort-aware Software Defect Prediction Metrics," 2025. [arXiv:2504.19181](https://arxiv.org/abs/2504.19181): initial false alarms beside hits in the backtest, *not built*.
- "On the Prevalence and Usage of Commit Signing on GitHub," *EASE* 2025. [arXiv:2504.19215](https://arxiv.org/abs/2504.19215): `signing.py`.
- "TypoSmart," 2025. [arXiv:2502.20528](https://arxiv.org/html/2502.20528v1): why typosquatting by edit distance is not done.
- "Detecting AI Coding Agents in Open Source: A Validated Multi-Method Census of 180 Million Repositories," 2026. [arXiv:2606.24429](https://arxiv.org/html/2606.24429v1): the trailer inventory in `provenance.py`, and why it keeps no list of products.
- "Attributing AI-generated commits at scale," 2026. [arXiv:2603.28592](https://arxiv.org/html/2603.28592v2): trailers and identities as the channels `provenance.py` reads.
- "Not All Agents Are Equal: Code Quality and Post-Merge Maintenance Across Five Autonomous Coding Agents in the Wild," 2026. [arXiv:2609.17598](https://arxiv.org/html/2609.17598): why the cohort in `provenance.py` imports no prior.
- Tornhill, *Your Code as a Crime Scene*, 2nd ed., Pragmatic Bookshelf, 2024. [sum of coupling](https://www.oreilly.com/library/view/your-code-as/9798888650837/f_0066.xhtml): hotspots by revisions × lines of code, `maat.soc` and the `changes alongside` reason.

## Tools and libraries

The tools gitmole runs, and why each, are in [tools.md](https://github.com/antvinni/gitmole/blob/main/docs/tools.md). These informed the rules without being run:

- code-maat (Adam Tornhill). [README](https://github.com/adamtornhill/code-maat/blob/master/README.md): the layout of `maat.py`, its temporal period behind `maat.changesets`, and `soc`.
- pyszz_v2 (Rosa et al.). [repo](https://github.com/grosa1/pyszz_v2/): the reference R-SZZ `szz.py` follows.
- Bus Factor Explorer (JetBrains Research). [repo](https://github.com/JetBrains-Research/bus-factor-explorer): the decay in `maat.doa`.
- py-tree-sitter and the tree-sitter grammar wheels (MIT). [repo](https://github.com/tree-sitter/py-tree-sitter): `structure.py`, behind `gitmole[structure]`.
- tree-sitter-language-pack 1.20.0. [PyPI](https://pypi.org/project/tree-sitter-language-pack/): considered and not used; it downloads its grammars at run time.
- lizard, issue #432. [issue](https://github.com/terryyin/lizard/issues/432): why cognitive complexity comes from `structure.py`.
- ast-grep-py. [PyPI](https://pypi.org/project/ast-grep-py/): shape rules, *not built*.
- difftastic. [repo](https://github.com/Wilfred/difftastic): why AST diff over history is not done.
- ossf/malicious-packages (OpenSSF). [repo](https://github.com/ossf/malicious-packages): `MAL-` advisories are critical in `deps.py`.
- deps-lsp issue #646. [issue](https://github.com/bug-ops/deps-lsp/issues/646): the same `MAL-` severity bug, elsewhere.
- trivy discussion #9070. [discussion](https://github.com/aquasecurity/trivy/discussions/9070): `partialFingerprints` in `sarif.py`.
- gitsign (Sigstore). [repo](https://github.com/sigstore/gitsign): the `x509` mechanism in `signing.py`.
- zizmor. [audits](https://docs.zizmor.sh/audits/): the `unpinned_actions` check, which gitmole does lexically.
- GuardDog (Datadog). [repo](https://github.com/DataDog/guarddog): the reference set behind `install_scripts`.
- license-expression (nexB). [PyPI](https://pypi.org/project/license-expression/): declared licences, *not built*.
- ecosyste-ms/typosquatting-dataset. [repo](https://github.com/ecosyste-ms/typosquatting-dataset): an exact-match list, *not built*.
- actions/attest (GitHub). [repo](https://github.com/actions/attest): the CI attestation of gitmole's own report.
- pnpm pull request #14902. [PR](https://github.com/pnpm/pnpm/pull/14902): why `lockfile_drift` reads commit times.

## Documentation, standards and specifications

- CodeScene, Code Health. [docs](https://docs.enterprise.codescene.io/latest/guides/technical/code-health.html): nesting and the bumpy road in `structure.py`, the `deep_nesting` finding.
- CodeScene, terminology. [docs](https://docs.enterprise.codescene.io/versions/6.0.8/terminology/codescene-terminology.html): ticket-ID grouping in `maat.changesets`.
- CodeScene, hotspots guide. [docs](https://docs.enterprise.codescene.io/versions/4.4.2/guides/technical/hotspots.html): the watch list by component and `component_coupling`.
- SonarSource, Cognitive Complexity. [PDF](https://www.sonarsource.com/docs/CognitiveComplexity.pdf): cognitive complexity in `structure.py`.
- GitHub, SARIF support for code scanning. [docs](https://docs.github.com/en/code-security/reference/code-scanning/sarif-files/sarif-support): `sarif.py`.
- GitLab, SARIF reports. [docs](https://docs.gitlab.com/user/application_security/detect/sarif/): every SARIF result needs a rule id and, to be kept, a location.
- GitHub, `.git-blame-ignore-revs`. [discussion](https://github.com/orgs/community/discussions/5033): declared commits left out in `maat.py`.
- git-cat-file(1). [man page](https://www.man7.org/linux//man-pages/man1/git-cat-file.1.html): `leaks.unreachable` and `signing.py`.
- gitmodules(5). [docs](https://git-scm.com/docs/gitmodules): the submodule checks in `hygiene.py`.
- Red Hat, RHSB-2021-007, CVE-2021-42574. [advisory](https://access.redhat.com/security/vulnerabilities/RHSB-2021-007): `trojan_source`.
- SLSA v1.2, source track. [spec](https://slsa.dev/spec/v1.2/source-requirements): signing coverage as evidence, never a level.
- OpenSSF, Open Source Project Security Baseline. [site](https://baseline.openssf.org/): the hygiene checks; tagging rules with controls is *not built*.
- OpenSSF Scorecard. [site](https://scorecard.dev/): the `scorecard` key on each hygiene rule.
- European Commission, Cyber Resilience Act. [site](https://digital-strategy.ec.europa.eu/en/policies/cyber-resilience-act): an SBOM emitter, *not built*.
- SPDX 3.0.1, AI profile. [spec](https://spdx.github.io/spdx-spec/v3.0.1/model/AI/AI/): why there is no `Generated-By` trailer to read.
- Linux kernel, coding assistants. [docs](https://docs.kernel.org/process/coding-assistants.html): `Assisted-by` in the cohort and the `signoff_by_co_author` finding.
- AGENTS.md. [site](https://agents.md/): the instruction files `provenance.py` reads.
- GitHub Copilot, custom instructions. [docs](https://docs.github.com/copilot/customizing-copilot/adding-custom-instructions-for-github-copilot): the instruction paths `provenance.py` reads.
- Claude Code, hooks reference. [docs](https://code.claude.com/docs/en/hooks): `--hook` output, and the approval settings `provenance.py` reads.
- Cursor, hooks. [docs](https://cursor.com/docs/hooks): `--hook`.
- Gemini CLI, hooks reference. [docs](https://github.com/google-gemini/gemini-cli/blob/main/docs/hooks/reference.md): `--hook`.
- pre-commit, creating new hooks. [docs](https://pre-commit.com/#creating-new-hooks): `.pre-commit-hooks.yaml`.
- Debian, Reproducible Builds. [wiki](https://wiki.debian.org/ReproducibleBuilds/About): the byte-identical JSON and its envelope.

## Industry reports and articles

- OpenSSF, "Detecting Malicious Packages Using the OSV API," May 2026. [post](https://openssf.org/blog/2026/05/20/detecting-malicious-packages-using-the-osv-api/): `MAL-` records in the offline database.
- Nesbitt, "Git submodules as a package manager," September 2026. [post](https://nesbitt.io/2026/09/01/git-submodules-as-a-package-manager.html): the submodule checks.
- Anchore, "SBOMs and the EU CRA." [post](https://anchore.com/sbom/eu-cra/): an SBOM emitter, *not built*.
- GitClear, "AI Code Quality and the Maintainability Gap," 2026, and "AI Assistant Code Quality," 2025. [2026](https://www.gitclear.com/the_ai_code_quality_maintainability_gap), [2025](https://www.gitclear.com/ai_assistant_code_quality_2025_research): the duplication rate a year back.
- CodeRabbit, "State of AI vs Human Code Generation." [post](https://www.coderabbit.ai/blog/state-of-ai-vs-human-code-generation-report): why the cohort imports no prior.
- Google Cloud, "Announcing the 2025 DORA Report." [post](https://cloud.google.com/blog/products/ai-machine-learning/announcing-the-2025-dora-report): the same.
- METR, "Measuring the Impact of Early-2025 AI on Experienced Open-Source Developer Productivity," July 2025. [post](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/): the same.
- Netwrix, on Trend Micro's MCP credential-storage research. [post](https://netwrix.com/en/resources/blog/ai-coding-assistant-credential-storage-risks/): `mcp_literal_env`.
- Codacy, "Deterministic Static Analysis for AI Coding Workflows." [post](https://blog.codacy.com/deterministic-static-analysis-for-ai-coding-workflows-how-to-cut-token-cost-without-weakening-code-review): `--hook`, deterministic findings before inference.
