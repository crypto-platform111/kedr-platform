# Software and asset provenance

Install the frontend with `npm ci --ignore-scripts` using `frontend/package-lock.json`, and the backend with `python -m pip install -r requirements.lock.txt`. See README.md for supported Python/Node versions and complete Windows setup. Runtimes, environments, installed packages and caches are excluded from source control.

Direct UI libraries use MIT (React, React Router, XYFlow, Vite), Apache-2.0 (ECharts), ISC (Lucide) and SIL Open Font License 1.1 (IBM Plex fonts). The full npm tree also declares BSD, MPL-2.0, CC-BY-4.0, BlueOak and 0BSD notices. [dependency-licenses.json](dependency-licenses.json) records public license metadata for all 216 npm lockfile entries and 27 pinned Python packages. [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt) retains upstream license/notice texts from the installed npm tree and the optional Node runtime notice. Runtime binaries are excluded. Installed packages retain their own licenses; consult those files for complete terms and preserve applicable notices when distributing bundled builds. The logo, page layout and product illustrations are original SVG/CSS/component work.

Historical installed-environment audit reports remain private and are not required to clone, start or test the platform. Review current upstream advisories and changed lockfiles before distribution.

Dependency metadata and version-based checks are not a security certification. Software licenses do not grant redistribution rights to exchange data. No historical prices, Binance archives, user records or private research reports are included. Historical-data access requires separately installed authorized sources; cloning does not install those datasets.

After installation, run `python -m pip check` and, inside `frontend`, `npm audit --json`. Optional `scripts/audit_v02.py` checks installed Python versions against public OSV metadata and runs npm audit; `scripts/collect_notices.py` collects installed npm notices. These write ignored local verification output and do not install packages or grant redistribution rights.

## 0.2 charting decision and dependency check

The studio keeps the pinned **ECharts 6.1.0** dependency. Its candlestick series, linked axes, zoom controls and separate grids support the local terminal without a second renderer or external market-data service. The replaceable `FinancialChart` adapter is in `frontend/src/charting.tsx`. ECharts LICENSE and NOTICE content is preserved in THIRD_PARTY_NOTICES.txt. [ECharts license](https://github.com/apache/echarts/blob/master/LICENSE), [official FAQ](https://echarts.apache.org/en/faq.html).

TradingView Lightweight Charts was also evaluated as a free alternative. It is distinct from proprietary TradingView chart products and has its own notice/attribution requirements. It was not installed: the existing ECharts dependency covers the implemented candle, volume, indicator and trace views. No proprietary chart license or paid data service was acquired. [Lightweight Charts project and attribution](https://github.com/tradingview/lightweight-charts/blob/master/README.md), [TradingView library comparison](https://www.tradingview.com/free-charting-libraries/).

No proprietary chart product, paid design asset pack or data subscription is required for the local demo workflow. Optional external AI requires separate provider configuration and explicit request consent.
