export const stationOptions = [
'Hat Yai Solar Farm',
'Songkhla Solar Farm',
'Nakhon Si Thammarat Solar Farm',
'Pattani Solar Farm',
'Trang Solar Farm'];


export const kpis = [
{
  id: 'pgen',
  label: 'กำลังผลิตรวมที่พยากรณ์ (P_gen)',
  value: '742',
  unit: 'kW',
  delta: '+6.2%',
  trend: 'up' as const,
  note: 'เทียบกับ 1 ชม. ก่อนหน้า',
  spark: [30, 34, 31, 38, 36, 42, 40, 47, 45, 52],
  tone: 'ok' as const
},
{
  id: 'ptarget',
  label: 'เป้าหมายการจ่ายไฟ (P_target)',
  value: '850',
  unit: 'kW',
  note: 'คงที่',
  spark: [50, 50, 50, 50, 50, 50, 50, 50, 50, 50],
  tone: 'brand' as const
},
{
  id: 'dp',
  label: 'ส่วนต่างกำลังผลิต (ΔP)',
  value: '108',
  unit: 'kW',
  delta: '-32.4%',
  trend: 'down' as const,
  note: '(สำรองมากขึ้น)',
  spark: [30, 32, 31, 36, 34, 40, 38, 44, 40, 46],
  tone: 'ok' as const
}];


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
{ t: '22:00', predicted: 225, band: [155, 300] }];


export const powerData = [
{ t: '19:00', gen: 800, target: 850 },
{ t: '19:30', gen: 775, target: 850 },
{ t: '20:00', gen: 740, target: 850 },
{ t: '20:30', gen: 680, target: 850 },
{ t: '21:00', gen: 580, target: 850 },
{ t: '21:30', gen: 510, target: 850 },
{ t: '22:00', gen: 430, target: 850 },
{ t: '22:30', gen: 360, target: 850 }].
map((d) => ({ ...d, gap: [d.gen, d.target] as [number, number] }));

export const cloudClasses = [
{ id: 'clear', name: 'Clear', th: 'ท้องฟ้าโปร่ง', pct: 7, tone: 'ok' as const },
{ id: 'inward', name: 'Inward', th: 'เคลื่อนที่เข้า', pct: 86, tone: 'brand' as const },
{ id: 'outward', name: 'Outward', th: 'เคลื่อนที่ออก', pct: 5, tone: 'warn' as const },
{ id: 'overcast', name: 'Overcast', th: 'เมฆปกคลุม', pct: 2, tone: 'muted' as const }];


export const alerts = [
{ id: 1, level: 'Warning' as const, title: 'เมฆกำลังเคลื่อนเข้า - เตรียมสำรองไฟ', station: 'Hat Yai Solar Farm', time: '20:32' },
{ id: 2, level: 'Critical' as const, title: 'GHI พยากรณ์ต่ำกว่าค่าจริงเกิน 20%', station: 'Hat Yai Solar Farm', time: '18:45' },
{ id: 3, level: 'Info' as const, title: 'โมเดล LSTM ทำงานเสร็จสิ้น', station: 'Hat Yai Solar Farm', time: '17:50' },
{ id: 4, level: 'Normal' as const, title: 'ระบบ Ingestion ดึงข้อมูลสำเร็จ', station: 'Songkhla Solar Farm', time: '16:32' },
{ id: 5, level: 'Info' as const, title: 'Re-training โมเดลเสร็จสิ้น', station: 'Nakhon Si Thammarat Solar Farm', time: '14:16' }];


export const stations = [
{ id: 1, name: 'Hat Yai Solar Farm', province: 'สงขลา', pgen: 742, ptarget: 850, online: true },
{ id: 2, name: 'Songkhla Solar Farm', province: 'สงขลา', pgen: 612, ptarget: 650, online: true },
{ id: 3, name: 'Nakhon Si Thammarat Solar Farm', province: 'นครศรีธรรมราช', pgen: 530, ptarget: 500, online: true },
{ id: 4, name: 'Pattani Solar Farm', province: 'ปัตตานี', pgen: 0, ptarget: 400, online: false },
{ id: 5, name: 'Trang Solar Farm', province: 'ตรัง', pgen: 0, ptarget: 450, online: false }];


export const decisionLog = [
{ id: 1, action: 'สั่งสำรองไฟ', station: 'Hat Yai Solar Farm', time: '20:33:10', tone: 'warn' as const },
{ id: 2, action: 'ปรับเป้าหมาย', station: 'Songkhla Solar Farm', time: '19:58:42', tone: 'warn' as const }];


export const services = [
{ id: 'ingest', name: 'Ingestion', ok: true },
{ id: 'lstm', name: 'LSTM', ok: true },
{ id: 'convlstm', name: 'ConvLSTM', ok: true },
{ id: 'sat', name: 'Satellite Feed', ok: true },
{ id: 'db', name: 'Database', ok: true }];