import { OnInit, OnDestroy, OnChanges, Input, Output, EventEmitter } from '@angular/core';
import * as L from 'leaflet';
import { Service } from '@wiz/libs/portal/season/service';

const analysisResponses = new Map<string, {at: number, value: Promise<any>}>();

export class Component implements OnInit, OnDestroy, OnChanges {
    @Input() embeddedRegion = '';
    @Input() embeddedTab = 'dashboard';
    @Output() stationNavigate = new EventEmitter<any>();
    @Output() navigate = new EventEmitter<string>();
    private initialized = false;
    public tab = 'dashboard';
    public periodBounds: any = {};
    public minDate = '';
    public maxDate = '';
    public dateStart = '';
    public dateEnd = '';
    public draftStart = '';
    public draftEnd = '';
    public periodError = '';
    public stability: any = null;
    public stabilityBusy = false;
    private responseGeneration = 0;
    public regionId = 'seoul';
    public allRegionsSelected = false;
    public regions: any[] = [];
    public overview: any = null;
    public dashboardNetwork: any = null;
    public dashboardRank: any = null;
    public dashboardExtra: any = null;
    public heatMax = 1;
    public research: any = null;
    public researchBusy = false;
    public researchError = '';
    public history: any = null;
    public historyBusy = false;
    private stationGeneration = 0;
    public stations: any[] = [];
    public stationTotal = 0;
    public stationSearch = '';
    public selectedStation: any = null;
    public network: any = null;
    public transitResult: any = null;
    public transitBusy = false;
    public transitError = "";
    public transitVisible = true;
    private transitMap: L.Map | null = null;
    private transitMarkers: L.LayerGroup | null = null;
    public centrality: any = null;
    public compare: any = null;
    public comparisonClusters: any = null;
    public compareRegions = ['seoul', 'daejeon', 'sejong'];
    public question = '';
    public lastQuestion = '';
    public answer: any = null;
    public busy = false;
    public error = '';
    public graphNodes: any[] = [];
    public graphEdges: any[] = [];
    private map: L.Map | null = null;
    private generation = 0;

    constructor(public service: Service) {}

    async ngOnInit() {
        await this.service.init();
        try {
            const result = await this.request('regions');
            this.regions = result.regions || [];
        } catch (error: any) {
            this.error = error.message;
        }
        if (this.embeddedRegion) {
            this.regionId = this.embeddedRegion;
            this.tab = this.embeddedTab;
        }
        const bounds = await this.request('period_bounds');
        this.periodBounds = bounds.regions;
        this.configurePeriod();
        this.initialized = true;
        await this.loadTab();
    }

    async ngOnChanges() {
        if (!this.initialized || !this.embeddedRegion) return;
        this.map?.remove(); this.map = null;
        this.regionId = this.embeddedRegion;
        this.tab = this.embeddedTab;
        this.selectedStation = null;
        await this.loadTab();
    }

    ngOnDestroy() { this.transitMap?.remove(); this.transitMap = null; this.generation++; this.initialized = false; this.map?.remove(); this.map = null; }

    private async request(action: string, extra: any = {}) {
        const params = { action, region_id: this.allRegionsSelected ? 'all' : this.regionId,
            ...(action === 'regions' || action === 'period_bounds' ? {} : {date_start:this.dateStart, date_end:this.dateEnd}), ...extra };
        const key = JSON.stringify(params);
        const saved = analysisResponses.get(key);
        if (action !== 'chat' && saved && Date.now() - saved.at < 300000) return saved.value;
        const value = (async () => {
            const response: any = await wiz.call('handle', params);
            if (response.code !== 200) throw new Error(response.data?.message || response.message || '분석 데이터를 불러오지 못했습니다.');
            return response.data;
        })();
        if (action !== 'chat') {
            analysisResponses.set(key, {at: Date.now(), value});
            value.catch(() => analysisResponses.delete(key));
        }
        return value;
    }

    public async loadResearch(current = this.generation) {
        this.researchBusy = true;
        this.researchError = '';
        try {
            const value = await this.request('research');
            if (current === this.generation) this.research = value;
        } catch (error: any) {
            if (current === this.generation) this.researchError = error.message;
        } finally {
            if (current === this.generation) {
                this.researchBusy = false;
                await this.service.render();
                if (this.tab === 'dashboard' && this.overview) this.renderMap();
            }
        }
    }

    public async changeTab(tab: string) {
        if (!['dashboard', 'stations', 'network', 'regions', 'agent'].includes(tab)) return;
        if (this.embeddedRegion) { this.navigate.emit(tab); return; }
        this.transitMap?.remove(); this.transitMap = null;
        if (tab !== 'dashboard') { this.map?.remove(); this.map = null; }
        this.tab = tab;
        this.configurePeriod();
        await this.loadTab();
    }

    public async selectAllRegions() {
        this.compareRegions = this.regions.map(region => region.region_id);
        this.allRegionsSelected = true;
        this.configurePeriod();
        await this.changeRegion();
    }

    public async selectRegion(regionId: string) {
        this.allRegionsSelected = false;
        this.regionId = regionId;
        this.configurePeriod();
        await this.changeRegion();
    }

    public async changeRegion() {
        this.map?.remove(); this.map = null;
        this.stationSearch = '';
        this.overview = null; this.dashboardNetwork = null; this.dashboardRank = null; this.dashboardExtra = null;
        this.transitMap?.remove(); this.transitMap = null; this.transitResult = null; this.transitError = ""; this.transitBusy = false;
        this.network = null; this.centrality = null; this.stations = []; this.stationTotal = 0;
        this.compare = null; this.comparisonClusters = null;
        this.stabilityBusy = false; this.historyBusy = false;
        this.selectedStation = null;
        this.research = null;
        this.history = null;
        this.stability = null;
        this.answer = null;
        this.lastQuestion = '';
        this.responseGeneration++;
        this.stationGeneration++;
        await this.loadTab();
    }

    public configurePeriod() {
        const key = this.allRegionsSelected || this.tab === 'regions' ? 'all' : this.regionId;
        const b = this.periodBounds[key] || {};
        this.minDate = b.min || '';
        this.maxDate = b.max || '';
        if (!b.available) this.dateStart = this.dateEnd = '';
        else if (!this.dateStart || !this.dateEnd || this.dateStart < this.minDate || this.dateEnd > this.maxDate)
            { this.dateStart = this.minDate; this.dateEnd = this.maxDate; }
        this.draftStart = this.dateStart; this.draftEnd = this.dateEnd;
        this.periodError = '';
    }

    public async applyPeriod() {
        if (!this.draftStart || !this.draftEnd || this.draftStart > this.draftEnd ||
            this.draftStart < this.minDate || this.draftEnd > this.maxDate) {
            this.periodError = '확보된 범위 안에서 시작일과 종료일을 선택하세요.';
            await this.service.render();
            return;
        }
        this.dateStart = this.draftStart; this.dateEnd = this.draftEnd;
        this.periodError = '';
        await this.changeRegion();
    }

    public async quickPeriod(days: number) {
        if (!this.maxDate) return;
        const end = this.dateEnd || this.maxDate;
        const date = new Date(end + 'T00:00:00Z');
        date.setUTCDate(date.getUTCDate() - days + 1);
        this.draftStart = [this.minDate, date.toISOString().slice(0,10)].sort().reverse()[0];
        this.draftEnd = end;
        await this.applyPeriod();
    }

    public async loadStability() {
        if (this.stabilityBusy) return;
        const current = this.generation;
        this.stabilityBusy = true;
        try {
            const value = await this.request('cluster_stability');
            if (current === this.generation) this.stability = value;
        } catch(error:any) { if (current === this.generation) this.error = error.message; }
        finally { if (current === this.generation) { this.stabilityBusy = false; await this.service.render(); } }
    }

    public stabilityRegions() {
        return this.stability?.regions || (this.stability ? [{...this.stability, region_name:this.nameOf(this.regionId)}] : []);
    }

    public historyBars() {
        const rows = (this.history?.windows || []).map((row:any)=>({...row,
            mean:row.observed_day_count ? row.rental_count/row.observed_day_count : null}));
        const max = Math.max(1,...rows.map((row:any)=>row.mean || 0));
        return rows.map((row:any)=>({...row,height:row.mean === null ? 0 : row.mean/max*100}));
    }

    public async selectGraphNode(id: string) {
        const item = this.network?.nodes?.find((x:any)=>x.station_id === id);
        const parts = id.split('::');
        await this.inspectStation(item?.original_station_id || parts[parts.length-1], item?.region_id || (parts.length > 1 ? parts[0] : this.regionId));
    }

    public async loadTab() {
        const current = ++this.generation;
        this.busy = true;
        this.error = '';
        this.researchBusy = false;
        try {
            if (['stations','network'].includes(this.tab)) {
                const overview = await this.request('overview');
                if (current !== this.generation) return;
                this.overview = overview;
            }
            if (this.tab === 'dashboard') {
                this.overview = null;
                this.dashboardNetwork = null;
                this.dashboardRank = null;
                this.dashboardExtra = null;
                const result = await this.request('overview');
                if (current !== this.generation) return;
                this.overview = result;
                void this.loadResearch(current);
                await this.service.render();
                if (current === this.generation) this.renderMap();
                await Promise.all([
                    this.request('network').then(async network => {
                        if (current !== this.generation) return;
                        this.dashboardNetwork = network;
                        this.makeGraph(network, 7);
                        await this.service.render();
                    }),
                    this.request('centrality').then(async rank => {
                        if (current !== this.generation) return;
                        this.dashboardRank = rank;
                        await this.service.render();
                    }),
                    this.request('dashboard_extra').then(async extra => {
                        if (current !== this.generation) return;
                        this.dashboardExtra = extra;
                        this.prepareDashboardExtra(extra);
                        await this.service.render();
                    })
                ]);
            } else if (this.tab === 'stations') {
                const result = await this.request('stations', { query: this.stationSearch });
                if (current !== this.generation) return;
                this.stations = result.stations || [];
                this.stationTotal = result.total || 0;
                void this.request('dashboard_extra').then(async extra => {
                    if (current !== this.generation) return;
                    this.dashboardExtra = extra; this.prepareDashboardExtra(extra);
                    await this.service.render();
                }).catch(error => { if (current === this.generation) this.error = error.message; });
                if (!this.selectedStation && this.stations.length) void this.openStation(this.stations[0]);
            } else if (this.tab === 'network') {
                void this.loadTransit(current);
                const result = await this.request('network');
                if (current !== this.generation) return;
                this.network = result;
                void this.loadResearch(current);
                this.makeGraph(result);
                const rank = await this.request('centrality');
                if (current !== this.generation) return;
                this.centrality = rank;
            } else if (this.tab === 'regions') {
                const result = await this.request('compare');
                if (current !== this.generation) return;
                this.compare = result;
                void this.request('compare_clusters').then(async result => {
                    if (current !== this.generation) return;
                    this.comparisonClusters = result;
                    await this.service.render();
                }).catch(error => { if (current === this.generation) this.error = error.message; });
            }
        } catch (error: any) {
            if (current === this.generation) this.error = error.message;
        } finally {
            if (current === this.generation) {
                this.busy = false;
                await this.service.render();
                if (this.tab === 'dashboard' && this.overview) setTimeout(() => { if (current === this.generation) this.renderMap(); }, 0);
            }
        }
    }

    public async searchStations() {
        if (this.tab === 'stations') await this.loadTab();
    }

    public async openStation(station: any) {
        const current = ++this.stationGeneration;
        const region = this.regionId;
        this.history = null;
        this.error = '';
        try {
            const value = await this.request('station', { station_id: station.station_key || station.station_id, station_region_id: station.region_id || '' });
            if (current !== this.stationGeneration || region !== this.regionId) return;
            this.selectedStation = value;
        } catch (error: any) {
            if (current === this.stationGeneration) this.error = error.message;
        } finally {
            await this.service.render();
        }
    }

    public async loadHistory() {
        const id = this.selectedStation?.station?.station_id;
        if (!id || this.historyBusy) return;
        const current = this.stationGeneration;
        this.historyBusy = true;
        try {
            const value = await this.request('station_history', {station_id: this.selectedStation.station.station_key || id, station_region_id: this.selectedStation.station.region_id || ''});
            if (current === this.stationGeneration) this.history = value;
        } catch (error: any) { this.error = error.message; }
        finally { this.historyBusy = false; await this.service.render(); }
    }

    public async inspectStation(id: string, city = '') {
        if (this.embeddedRegion) { this.stationNavigate.emit({region_id:this.regionId, station_id:id}); return; }
        await this.changeTab('stations');
        const station = this.stations.find(item => item.station_id === id && (!city || item.region_id === city)) || {station_id:id, region_id:city};
        await this.openStation(station);
    }

    public async navigateToStation(selection: any) {
        this.allRegionsSelected = false;
        this.regionId = selection.region_id;
        this.selectedStation = null;
        await this.inspectStation(selection.station_id);
    }

    public findings() {
        const types = this.research?.types || {};
        return [
            {label:'숨은 연결 거점', tone:'mint', row:types.low_usage_high_connectivity?.[0], kind:'rank'},
            {label:'시간대 집중', tone:'purple', row:types.time_concentrated?.[0], kind:'time'},
            {label:'불균형 후보', tone:'coral', row:types.persistent_imbalance?.[0], kind:'flow'}
        ];
    }

    public pageTitle() {
        const titles: any = {dashboard:'공공자전거 이용 현황과 숨은 연결 거점 분석', stations:'대여소 이용 특성 분석',
            network:'이동 패턴 분석', regions:'도시 간 비교', agent:'AI 분석 리포트'};
        return titles[this.tab] || 'Bike Link Analysis';
    }

    public peakHour() {
        const values = this.selectedStation?.profile?.hourly;
        return values?.length && values.some((x:number) => x > 0) ? values.indexOf(Math.max(...values)) : null;
    }

    public patternPoints(values: number[] | null, maximum?: number) {
        if (!values?.length) return '';
        const max = maximum || Math.max(1, ...values);
        return values.map((v,i) => (8 + i * 284 / Math.max(1,values.length-1)) + ',' + (90 - v/max * 74)).join(' ');
    }

    public stationLines() {
        const p = this.selectedStation?.profile;
        const max = Math.max(1, ...(p?.hourly || []), ...(p?.return_hourly || []));
        return [{name:'대여', color:'#1984f4', points:this.patternPoints(p?.hourly,max)},
            {name:'반납', color:'#13bca0', points:this.patternPoints(p?.return_hourly,max)}];
    }

    public comparisonLines() {
        const rows = (this.compare?.common || []).filter((x:any) => x.hourly?.length);
        const values = rows.map((x:any) => {
            const total = x.hourly.reduce((a:number,b:number) => a+b,0);
            return x.hourly.map((v:number) => total ? v/total*100 : 0);
        });
        const max = Math.max(1, ...values.flat());
        return rows.map((x:any,i:number) => ({name:x.region_name, color:i ? '#14ba9b':'#2683f2',
            points:this.patternPoints(values[i], max)}));
    }

    public weekdayRows() {
        return Array.from({length:7},(_,i) => ({name:['월','화','수','목','금','토','일'][i],
            values:(this.compare?.common || []).map((x:any) => {
                const total = (x.weekday || []).reduce((a:number,b:any)=>a+b.rental_count,0);
                return total ? (x.weekday?.[i]?.rental_count || 0)/total*100 : null;
            })}));
    }

    public clusterShare(cluster: any, city: any) {
        const total = (city.clusters || []).reduce((sum:number,row:any)=>sum+row.station_count,0);
        return total ? cluster.station_count/total*100 : 0;
    }

    public selectedClusterCities() {
        return (this.comparisonClusters?.regions || []).filter((x:any)=>this.compareRegions.includes(x.region_id));
    }

    public networkEdgeWidth(count: number) {
        const maximum = Math.max(1,...(this.network?.edges || []).map((x:any)=>x.trip_count));
        return .2 + count/maximum*1.2;
    }

    public annualValues() { return this.annualRows().map((x:any) => x.rental_count); }

    public annualRows() { return (this.compare?.annual || []).filter((x:any)=>x.region_id === 'sejong'); }


    private async loadTransit(current: number) {
        this.transitBusy = true; this.transitResult = null; this.transitError = "";
        try {
            const result = await this.request('transit_vulnerability');
            if (current !== this.generation) return;
            this.transitResult = result;
            await this.service.render();
            setTimeout(()=>{if(current === this.generation && this.tab === 'network') this.renderTransitMap();},0);
        } catch(error:any) {
            if(current === this.generation) this.transitError = error.message;
        } finally {
            if(current === this.generation) {this.transitBusy = false; await this.service.render();}
        }
    }
    public toggleTransit() {
        this.transitVisible = !this.transitVisible;
        if(!this.transitMap || !this.transitMarkers) return;
        if(this.transitVisible) this.transitMarkers.addTo(this.transitMap);
        else this.transitMarkers.removeFrom(this.transitMap);
    }
    private renderTransitMap() {
        const element = document.getElementById('bike-transit-map');
        if(!element) return;
        this.transitMap?.remove();
        this.transitMap = L.map(element, {scrollWheelZoom:false});
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
          attribution:'&copy; OpenStreetMap contributors', maxZoom:19}).addTo(this.transitMap);
        this.transitMarkers = L.layerGroup();
        const bounds: L.LatLngExpression[] = [];
        for(const row of this.transitResult?.candidates || []) {
            const point: L.LatLngExpression = [row.latitude,row.longitude];
            bounds.push(point);
            const marker = L.circleMarker(point,{radius:9,color:'#a3432e',fillColor:'#df704f',fillOpacity:.8});
            const caption = document.createElement('span');
            caption.textContent = row.station_id + ' · '+ row.nearest_stop_distance_m.toFixed(1) + 'm · 대여 ' + row.rental_count + '건';
            marker.bindPopup(caption).on('click',()=>{void this.inspectStation(row.station_id,row.region_id);});
            marker.addTo(this.transitMarkers);
        }
        if(this.transitVisible) this.transitMarkers.addTo(this.transitMap);
        if(bounds.length) this.transitMap.fitBounds(L.latLngBounds(bounds).pad(.15),{maxZoom:13});
        else this.transitMap.setView([37.5665,126.978],11);
        setTimeout(()=>this.transitMap?.invalidateSize(),100);
    }

    public flowBars() {
        const values = this.research?.types?.persistent_imbalance?.[0]?.hourly_net_outflow || [];
        const max = Math.max(1,...values.map((x:number)=>Math.abs(x)));
        return values.map((value:number,hour:number)=>({value,hour,height:Math.abs(value)/max*48}));
    }

    public async ask() {
        const message = this.question.trim();
        if (!message || this.busy) return;
        const current = ++this.responseGeneration;
        this.lastQuestion = message; this.busy = true; this.error = ''; this.answer = null;
        await this.service.render();
        try {
            const selected = this.selectedStation?.station;
            const effectiveQuestion = selected && /선택|해당|특정|이 대여소/.test(message) && !/ST-?\d+/i.test(message)
                ? message + '\n선택 대여소: ' + selected.region_name + ' ' + selected.station_id : message;
            const value = await this.request('chat', {message:effectiveQuestion});
            if (current === this.responseGeneration) this.answer = value;
        } catch(error:any) { if (current === this.responseGeneration) this.error = error.message; }
        finally { if (current === this.responseGeneration) {this.busy = false; await this.service.render();} }
    }

    public hourBars(values: number[] | null) {
        if (!values?.length) return [];
        const max = Math.max(1, ...values);
        return values.map((value, hour) => ({ hour, value, height: Math.max(2, value / max * 100) }));
    }

    public dailyBars(items: any[]) {
        if (!items?.length) return [];
        const max = Math.max(1, ...items.map(item => item.rental_count || 0));
        return items.map(item => ({ ...item, height: Math.max(2, item.rental_count / max * 100) }));
    }

    public nameOf(regionId: string) {
        return this.regions.find(item => item.region_id === regionId)?.region_name || regionId;
    }

    public compareItem(regionId: string) {
        return this.compare?.regions?.find((item: any) => item.region_id === regionId);
    }

    public selectedCompareItems() {
        return (this.compare?.regions || []).filter((item: any) => this.compareRegions.includes(item.region_id));
    }

    public async toggleCompareRegion(regionId: string) {
        if (this.compareRegions.includes(regionId)) {
            if (this.compareRegions.length <= 2) return;
            this.compareRegions = this.compareRegions.filter(item => item !== regionId);
        } else {
            this.compareRegions = [...this.compareRegions, regionId];
        }
        this.allRegionsSelected = this.regions.length > 0 &&
            this.regions.every(region => this.compareRegions.includes(region.region_id));
        await this.service.render();
    }

    public compareBarWidth(region: any, key: string) {
        const values = this.selectedCompareItems().map((item: any) => Number(item?.[key]) || 0);
        const maximum = Math.max(1, ...values);
        return region?.[key] === null || region?.[key] === undefined
            ? 0 : Math.max(3, Number(region[key]) / maximum * 100);
    }

    public sharePercent(value: number | null) {
        return value === null || value === undefined ? null : value * 100;
    }

    public sourceLabel(item: any) {
        if (!item) return '자료 확인 중';
        if (item.verification_status === 'VERIFIED') return '공식 출처 확인 자료';
        if (item.verification_status === 'METADATA_ONLY') return '메타데이터만 확보';
        return '자료 미확보';
    }

    public periodLabel() {
        if (this.dateStart && this.dateEnd) return this.dateStart + ' ~ ' + this.dateEnd + (this.allRegionsSelected || this.tab === 'regions' ? ' (공통)' : '');
        if (this.overview?.region_id !== this.regionId) return '지역별 확보 기간';
        return (this.overview.period_start || '기간 미확보') + ' ~ ' +
            (this.overview.period_end || '기간 미확보');
    }

    public heatColor(value: number) {
        const ratio = value / Math.max(1, this.heatMax);
        if (ratio > 0.78) return '#f45f65';
        if (ratio > 0.58) return '#ffc86d';
        if (ratio > 0.38) return '#e9ef98';
        if (ratio > 0.18) return '#78d8c5';
        return '#91c4f6';
    }

    public comparisonComparable() {
        const rows = this.dashboardExtra?.comparison || [];
        return rows.length === 2 && rows[0].observed_dates?.length > 0 &&
            JSON.stringify(rows[0].observed_dates) === JSON.stringify(rows[1].observed_dates);
    }

    public comparisonPercent(value: number) {
        const rows = this.dashboardExtra?.comparison || [];
        const maximum = Math.max(1, ...rows.map((row: any) => row.total_rentals || 0));
        return Math.max(3, value / maximum * 100);
    }

    private prepareDashboardExtra(extra: any) {
        this.heatMax = Math.max(1, ...(extra.heatmap || []).flatMap((row: any) => row.hours || []));
        const points = extra.cluster_points || [];
        if (!points.length) return;
        const xs = points.map((item: any) => item.x), ys = points.map((item: any) => item.y);
        const minX = Math.min(...xs), maxX = Math.max(...xs);
        const minY = Math.min(...ys), maxY = Math.max(...ys);
        extra.cluster_points = points.map((item: any) => ({
            ...item,
            px: 10 + (item.x - minX) / Math.max(0.001, maxX - minX) * 80,
            py: 88 - (item.y - minY) / Math.max(0.001, maxY - minY) * 76
        }));
    }

    public edgeName(id: string) {
        return this.dashboardNetwork?.nodes?.find((item: any) => item.station_id === id)?.station_name || id;
    }

    public rankPercent(value: number) {
        const maximum = this.dashboardRank?.rankings?.[0]?.pagerank || 1;
        return Math.max(3, value / maximum * 100);
    }

    public edgePercent(count: number) {
        const max = this.dashboardNetwork?.edges?.[0]?.trip_count || 1;
        return Math.max(5, count / max * 100);
    }

    private renderMap() {
        const element = document.getElementById('bike-leaflet-map-' + this.regionId);
        if (!element || this.tab !== 'dashboard') return;
        this.map?.remove();
        this.map = L.map(element, { scrollWheelZoom: false, zoomControl: false });
        L.control.zoom({ position: 'topright' }).addTo(this.map);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; OpenStreetMap contributors',
            maxZoom: 19
        }).addTo(this.map);
        const rows = (this.overview?.map_stations || []).filter((item: any) =>
            Number.isFinite(item.latitude) && Number.isFinite(item.longitude));
        if (!rows.length) { this.map.setView([37.5665, 126.978], 10); return; }
        const bounds: L.LatLngTuple[] = [];
        for (const item of rows) {
            const point: L.LatLngTuple = [item.latitude, item.longitude];
            const types = this.research?.types || {};
            const hidden = (types.low_usage_high_connectivity || []).some((row:any)=>row.station_id === item.station_id && (!row.region_id || row.region_id === item.region_id));
            const imbalance = (types.persistent_imbalance || []).some((row:any)=>row.station_id === item.station_id && (!row.region_id || row.region_id === item.region_id));
            const concentrated = (types.time_concentrated || []).some((row:any)=>row.station_id === item.station_id && (!row.region_id || row.region_id === item.region_id));
            const color = hidden ? '#08ad98' : imbalance ? '#f59842' : concentrated ? '#a45edc' : '#328bed';
            bounds.push(point);
            const caption = document.createElement('div');
            const name = document.createElement('strong');
            name.textContent = item.station_id + ' · ' + (item.station_name || '') + (hidden ? ' · 숨은 연결 후보' : imbalance ? ' · 불균형 후보' : concentrated ? ' · 시간대 집중 후보' : '');
            caption.appendChild(name);
            L.circleMarker(point, { radius: 5, color: color, weight: 1.5,
                fillColor: color, fillOpacity: 0.8 }).addTo(this.map).bindPopup(caption).on('click', () => { void this.inspectStation(item.station_id, item.region_id); });
        }
        this.map.fitBounds(L.latLngBounds(bounds).pad(0.12), { maxZoom: 12 });
        setTimeout(() => this.map?.invalidateSize(), 100);
    }

    private makeGraph(network: any, limit = 12) {
        const edges = (network?.edges || []).slice(0, limit);
        const ids = Array.from(new Set(edges.flatMap((item: any) => [item.origin_station_id, item.destination_station_id])));
        const names: any = {};
        for (const item of network?.nodes || []) names[item.station_id] = item.station_name || item.station_id;
        this.graphNodes = ids.map((id: any, index: number) => ({
            id, name: String(id),
            x: 50 + 35 * Math.cos(index * 2 * Math.PI / Math.max(1, ids.length)),
            y: 50 + 35 * Math.sin(index * 2 * Math.PI / Math.max(1, ids.length))
        }));
        const byId: any = {};
        for (const item of this.graphNodes) byId[item.id] = item;
        this.graphEdges = edges.map((item: any) => ({
            ...item, x1: byId[item.origin_station_id]?.x, y1: byId[item.origin_station_id]?.y,
            x2: byId[item.destination_station_id]?.x, y2: byId[item.destination_station_id]?.y
        }));
    }
}
