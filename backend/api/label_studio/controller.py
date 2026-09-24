from fastapi import Depends, HTTPException, status

from api.auth.model import User
from api.auth.service import get_current_user
from api.label_studio.schema import CreateProjectRequest, ImportTaskRequest, ProjectResponse, TaskResponse
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
