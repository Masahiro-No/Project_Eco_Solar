from fastapi import Depends, HTTPException, status

from core.config import settings
from api.auth.model import User
from api.auth.service import get_current_user
from api.jobs.service import JobService
from api.label_studio.schema import (
    AnnotationResponse,
    CreateAnnotationRequest,
    CreateProjectRequest,
    ImportTaskRequest,
    ProjectResponse,
    SubmitSatelliteAnnotationRequest,
    SubmitSatelliteAnnotationResponse,
    TaskResponse,
)
from api.label_studio.service import LabelStudioService

# ==========================================
# 1. สร้าง Dictionary เก็บ Template XML ที่พบบ่อย
# ==========================================
CONFIG_TEMPLATES = {
    # สำหรับจำแนกประเภทข้อความ (Text Classification)
    "text_class": """<View>
  <Text name="text" value="$text"/>
  <Choices name="label" toName="text">
    <Choice value="Positive"/>
    <Choice value="Neutral"/>
    <Choice value="Negative"/>
  </Choices>
</View>""",

    # สำหรับตีกรอบรูปภาพ (Image Object Detection - Bounding Box)
    "image_bbox": """<View>
  <Image name="image" value="$image"/>
  <RectangleLabels name="label" toName="image">
    <Label value="Dog" background="red"/>
    <Label value="Cat" background="blue"/>
  </RectangleLabels>
</View>""",

    # สำหรับจำแนกประเภทรูปภาพ (Image Classification)
    "image_class": """<View>
  <Image name="image" value="$image"/>
  <Choices name="choice" toName="image">
    <Choice value="Cat"/>
    <Choice value="Dog"/>
  </Choices>
</View>""",

    # สำหรับไฮไลต์คำในประโยค (Named Entity Recognition - NER)
    "text_ner": """<View>
  <Labels name="label" toName="text">
    <Label value="Person" background="red"/>
    <Label value="Organization" background="darkorange"/>
    <Label value="Location" background="green"/>
  </Labels>
  <Text name="text" value="$text"/>
</View>""",

    # สำหรับถอดเสียง (Audio Transcription)
    "audio_trans": """<View>
  <Audio name="audio" value="$audio"/>
  <TextArea name="transcription" toName="audio" rows="4" editable="true"/>
</View>""",

    # สำหรับตรวจทานค่ารังสีแสงอาทิตย์ GHI Ground Truth
    "solar_ghi_verify": """<View>
  <Header value="Solar GHI Ground Truth Verification"/>
  <Text name="station" value="$station_id"/>
  <Text name="timestamp" value="$timestamp"/>
  <Number name="ghi" toName="station" required="true" min="0" max="1500"/>
  <Choices name="quality" toName="station">
    <Choice value="High Quality"/>
    <Choice value="Suspected Cloud Enhancement"/>
    <Choice value="Sensor Noise"/>
  </Choices>
</View>""",

    # สำหรับตรวจทานภาพเมฆดาวเทียม Himawari
    "satellite_cloud_verify": """<View>
  <Header value="Himawari Satellite Cloud Pattern Verification"/>
  <Image name="satellite_crop" value="$satellite_image"/>
  <Choices name="cloud_motion" toName="satellite_crop">
    <Choice value="Clear"/>
    <Choice value="Inward (Approaching Farm)"/>
    <Choice value="Outward (Leaving Farm)"/>
    <Choice value="Overcast (Stationary)"/>
  </Choices>
</View>"""
}

async def list_projects(
    _: User = Depends(get_current_user),
) -> list[ProjectResponse]:
    svc = LabelStudioService()
    try:
        projects = svc.list_projects()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Label Studio error: {e}") from None
    return [ProjectResponse(id=p.id, title=p.title, task_number=p.task_number) for p in projects]


async def create_project(
    payload: CreateProjectRequest,
    _: User = Depends(get_current_user),
) -> ProjectResponse:
    svc = LabelStudioService()
    
    # ==========================================
    # 2. ดักจับ input และจับคู่กับ Template
    # ==========================================
    actual_label_config = payload.label_config.strip()
    
    # ถ้า Frontend ส่ง Keyword ที่มีใน Dictionary มา (เช่น "image_bbox")
    if actual_label_config in CONFIG_TEMPLATES:
        actual_label_config = CONFIG_TEMPLATES[actual_label_config]
        
    # ถ้าส่งค่าว่าง หรือส่งคำว่า "string" มาดื้อๆ ให้ใช้ Default เป็น Text Classification
    elif actual_label_config == "string" or not actual_label_config:
        actual_label_config = CONFIG_TEMPLATES["text_class"]
        
    # หมายเหตุ: ถ้า Frontend ส่ง XML เข้ามาตรงๆ เลย (ไม่ตรงเงื่อนไขด้านบน) 
    # โค้ดนี้ก็จะปล่อยผ่าน (Pass through) ค่า XML นั้นไปหา Label Studio เลย 
    # ซึ่งช่วยให้ยืดหยุ่นในกรณีที่ Frontend อยากส่ง Custom XML เองในอนาคต

    try:
        p = svc.create_project(payload.title, actual_label_config)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Label Studio error: {e}") from None
    
    return ProjectResponse(id=p.id, title=p.title, task_number=p.task_number)


async def list_tasks(
    project_id: int,
    _: User = Depends(get_current_user),
) -> list[TaskResponse]:
    svc = LabelStudioService()
    try:
        tasks = svc.list_tasks(project_id)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Label Studio error: {e}") from None
    return [TaskResponse(id=t.id, data=t.data) for t in tasks]


async def create_task(
    project_id: int,
    payload: ImportTaskRequest,
    _: User = Depends(get_current_user),
) -> TaskResponse:
    svc = LabelStudioService()
    try:
        t = svc.create_task(project_id, payload.data)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Label Studio error: {e}") from None
    return TaskResponse(id=t.id, data=t.data)


async def list_annotations(
    _: int,
    task_id: int,
    __: User = Depends(get_current_user),
) -> list[AnnotationResponse]:
    svc = LabelStudioService()
    try:
        annotations = svc.list_annotations(task_id)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Label Studio error: {e}") from None
    return [AnnotationResponse(id=a.id, task_id=task_id, result=getattr(a, "result", [])) for a in annotations]


async def create_annotation(
    _: int,
    task_id: int,
    payload: CreateAnnotationRequest,
    __: User = Depends(get_current_user),
) -> AnnotationResponse:
    svc = LabelStudioService()
    try:
        ann = svc.create_annotation(task_id=task_id, result=payload.result, ground_truth=payload.ground_truth)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Label Studio error: {e}") from None
    return AnnotationResponse(id=ann.id, task_id=task_id, result=payload.result)


async def submit_satellite_annotation(
    payload: SubmitSatelliteAnnotationRequest,
    _: User = Depends(get_current_user),
) -> SubmitSatelliteAnnotationResponse:
    """Submit satellite cloud verification -> Label Studio -> Buffer check -> retrain trigger."""
    svc = LabelStudioService()
    project_title = "Himawari Satellite Cloud Pattern Verification"
    label_cfg = CONFIG_TEMPLATES["satellite_cloud_verify"]

    # 1. Get or create project in Label Studio
    try:
        p = svc.get_or_create_project(project_title, label_cfg)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Label Studio project error: {e}") from None

    # 2. Create task
    task_data = {
        "station_id": payload.station_id,
        "timestamp": payload.timestamp,
        "satellite_image": f"/satellite-cache/{payload.station_id}_latest.png",
        "cloud_condition": payload.cloud_condition,
        "cloud_index": payload.cloud_index,
        "sequence_id": payload.sequence_id,
    }
    try:
        t = svc.create_task(p.id, task_data)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to create task in Label Studio: {e}") from None

    # 3. Create annotation
    annotation_result = [
        {
            "value": {"choices": [payload.cloud_condition]},
            "from_name": "cloud_motion",
            "to_name": "satellite_crop",
            "type": "choices",
        }
    ]
    try:
        ann = svc.create_annotation(task_id=t.id, result=annotation_result, ground_truth=True)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to create annotation in Label Studio: {e}") from None

    # 4. Check Buffer in Redis
    retrain_enqueued = False
    retrain_status = "accumulating"
    accumulated_count = 1
    threshold = settings.convlstm_retrain_threshold

    try:
        pool = await JobService.get_pool()
        accumulated_count = await pool.incr("convlstm_labeled_buffer_count")
        await pool.close()
    except Exception:
        pass

    if accumulated_count >= threshold:
        if settings.enable_retrain:
            try:
                import json
                job_payload = {
                    "station_id": payload.station_id,
                    "accumulated_count": accumulated_count,
                    "threshold": threshold,
                }
                await JobService.enqueue("train_convlstm_nowcaster", json.dumps(job_payload), queue_name="train_queue")
                retrain_enqueued = True
                retrain_status = f"threshold_reached ({accumulated_count}/{threshold}) - enqueued"
                # Reset counter
                pool = await JobService.get_pool()
                await pool.set("convlstm_labeled_buffer_count", 0)
                await pool.close()
            except Exception as e:
                retrain_status = f"enqueue_failed: {e}"
        else:
            retrain_status = f"threshold_reached ({accumulated_count}/{threshold}) - retrain_disabled (standby)"
    else:
        retrain_status = f"accumulating ({accumulated_count}/{threshold}) - {'ready' if settings.enable_retrain else 'standby'}"

    return SubmitSatelliteAnnotationResponse(
        task_id=t.id,
        annotation_id=ann.id,
        station_id=payload.station_id,
        accumulated_count=accumulated_count,
        threshold=threshold,
        retrain_enqueued=retrain_enqueued,
        retrain_status=retrain_status,
    )

