export const stationOptions = [
  'PSU Hat Yai Solar Farm (ม.อ. หาดใหญ่)',
  'Songkhla Solar Farm (พพ. สงขลา)',
  'Nakhon Si Thammarat Solar Farm',
  'Pattani Solar Farm',
  'Trang Solar Farm'
];

export const kpis = [
  {
    id: 'pgen',
    label: 'กำลังผลิตรวมที่พยากรณ์ (P_gen)',
    value: '4,250',
    unit: 'kW',
    delta: '+8.4%',
    trend: 'up' as const,
    note: 'เทียบกับ 1 ชม. ก่อนหน้า',
    spark: [30, 34, 31, 38, 36, 42, 40, 47, 45, 52],
    tone: 'ok' as const
  },
  {
    id: 'ptarget',
    label: 'เป้าหมายการจ่ายไฟ (P_target)',
    value: '5,000',
    unit: 'kW',
    note: 'เป้าหมายสถานี ST-001',
    spark: [50, 50, 50, 50, 50, 50, 50, 50, 50, 50],
    tone: 'brand' as const
  },
  {
    id: 'dp',
    label: 'ส่วนต่างกำลังผลิต (ΔP)',
    value: '750',
    unit: 'kW',
    delta: '-15.2%',
    trend: 'down' as const,
    note: '(สำรองไฟตามเกณฑ์)',
    spark: [30, 32, 31, 36, 34, 40, 38, 44, 40, 46],
    tone: 'ok' as const
  }
];

export const ghiData = [
  { t: '19:00', actual: 810, predicted: 790, band: [760, 820] },
  { t: '19:15', actual: 720, predicted: 715, band: [690, 745] },
  { t: '19:30', actual: 670, predicted: 640, band: [610, 680] },
  { t: '19:45', actual: 625, predicted: 620, band: [585, 660] },
  { t: '20:00', actual: 580, predicted: 580, band: [540, 625] },
  { t: '20:15', predicted: 500, band: [450, 555] },
  { t: '20:30', predicted: 440, band: [385, 500] },
  { t: '20:45', predicted: 390, band: [330, 455] },
  { t: '21:00', predicted: 345, band: [285, 410] },
  { t: '21:15', predicted: 310, band: [245, 380] },
  { t: '21:30', predicted: 280, band: [210, 350] },
  { t: '21:45', predicted: 250, band: [180, 325] },
  { t: '22:00', predicted: 225, band: [155, 300] }
];

export const powerData = [
  { t: '19:00', gen: 4200, target: 5000 },
  { t: '19:30', gen: 4050, target: 5000 },
  { t: '20:00', gen: 3800, target: 5000 },
  { t: '20:30', gen: 3450, target: 5000 },
  { t: '21:00', gen: 3000, target: 5000 },
  { t: '21:30', gen: 2600, target: 5000 },
  { t: '22:00', gen: 2150, target: 5000 },
  { t: '22:30', gen: 1800, target: 5000 }
].map((d) => ({ ...d, gap: [d.gen, d.target] as [number, number] }));

export const cloudClasses = [
  { id: 'clear', name: 'Clear', th: 'ท้องฟ้าโปร่ง', pct: 7, tone: 'ok' as const },
  { id: 'inward', name: 'Inward', th: 'เคลื่อนที่เข้า', pct: 86, tone: 'brand' as const },
  { id: 'outward', name: 'Outward', th: 'เคลื่อนที่ออก', pct: 5, tone: 'warn' as const },
  { id: 'overcast', name: 'Overcast', th: 'เมฆปกคลุม', pct: 2, tone: 'muted' as const }
];

export const alerts = [
  { id: 1, level: 'Warning' as const, title: 'เมฆกำลังเคลื่อนเข้า - เตรียมสำรองไฟ', station: 'PSU Hat Yai Solar Farm', time: '20:32' },
  { id: 2, level: 'Critical' as const, title: 'GHI พยากรณ์ต่ำกว่าค่าจริงเกิน 20%', station: 'PSU Hat Yai Solar Farm', time: '18:45' },
  { id: 3, level: 'Info' as const, title: 'โมเดล LSTM ทำงานเสร็จสิ้น', station: 'PSU Hat Yai Solar Farm', time: '17:50' },
  { id: 4, level: 'Normal' as const, title: 'ระบบ Ingestion ดึงข้อมูลสำเร็จ', station: 'Songkhla Solar Farm', time: '16:32' },
  { id: 5, level: 'Info' as const, title: 'Re-training โมเดลเสร็จสิ้น', station: 'Nakhon Si Thammarat Solar Farm', time: '14:16' }
];

export interface StationDashboardItem {
  id: string; // "ST-001", "ST-002" matching Backend Station.id
  name: string;
  province: string;
  latitude: number;
  longitude: number;
  panel_area: number;
  efficiency: number;
  target_capacity_kw: number;
  is_active: boolean;
  pgen: number;
  ptarget: number;
  online: boolean;
  inverters?: string;
  pr?: string;
  temp?: string;
}

export const stations: StationDashboardItem[] = [
  {
    id: 'ST-001',
    name: 'PSU Hat Yai Solar Farm (ม.อ. หาดใหญ่)',
    province: 'สงขลา',
    latitude: 7.0086,
    longitude: 100.4988,
    panel_area: 30000.0,
    efficiency: 0.185,
    target_capacity_kw: 5000.0,
    is_active: true,
    pgen: 4250,
    ptarget: 5000,
    online: true,
    inverters: '10/10',
    pr: '86.4%',
    temp: '32.5°C'
  },
  {
    id: 'ST-002',
    name: 'Songkhla Solar Farm (พพ. สงขลา)',
    province: 'สงขลา',
    latitude: 7.1982,
    longitude: 100.5954,
    panel_area: 24000.0,
    efficiency: 0.185,
    target_capacity_kw: 4000.0,
    is_active: true,
    pgen: 3420,
    ptarget: 4000,
    online: true,
    inverters: '8/8',
    pr: '84.2%',
    temp: '33.1°C'
  },
  {
    id: 'ST-003',
    name: 'Nakhon Si Thammarat Solar Farm',
    province: 'นครศรีธรรมราช',
    latitude: 8.4304,
    longitude: 99.9631,
    panel_area: 18000.0,
    efficiency: 0.190,
    target_capacity_kw: 3000.0,
    is_active: true,
    pgen: 2650,
    ptarget: 3000,
    online: true,
    inverters: '6/6',
    pr: '88.1%',
    temp: '31.8°C'
  },
  {
    id: 'ST-004',
    name: 'Pattani Solar Farm',
    province: 'ปัตตานี',
    latitude: 6.8696,
    longitude: 101.2501,
    panel_area: 15000.0,
    efficiency: 0.180,
    target_capacity_kw: 2500.0,
    is_active: false,
    pgen: 0,
    ptarget: 2500,
    online: false,
    inverters: '0/5',
    pr: '—',
    temp: '34.0°C'
  },
  {
    id: 'ST-005',
    name: 'Trang Solar Farm',
    province: 'ตรัง',
    latitude: 7.5563,
    longitude: 99.6114,
    panel_area: 16500.0,
    efficiency: 0.185,
    target_capacity_kw: 2750.0,
    is_active: false,
    pgen: 0,
    ptarget: 2750,
    online: false,
    inverters: '0/5',
    pr: '—',
    temp: '31.2°C'
  }
];

export const decisionLog = [
  { id: 1, action: 'สั่งสำรองไฟ', station: 'PSU Hat Yai Solar Farm', time: '20:33:10', tone: 'warn' as const },
  { id: 2, action: 'ปรับเป้าหมาย', station: 'Songkhla Solar Farm', time: '19:58:42', tone: 'warn' as const }
];

export const services = [
  { id: 'ingest', name: 'Ingestion', ok: true },
  { id: 'lstm', name: 'LSTM', ok: true },
  { id: 'convlstm', name: 'ConvLSTM', ok: true },
  { id: 'sat', name: 'Satellite Feed', ok: true },
  { id: 'db', name: 'Database', ok: true }
];