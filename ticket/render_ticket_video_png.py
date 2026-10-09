from PIL import Image, ImageDraw, ImageFont

W, H, S = 1800, 1300, 2
im = Image.new("RGB", (W, H), "white")
d = ImageDraw.Draw(im)
font_path = r"C:\Windows\Fonts\msyh.ttc"
f = ImageFont.truetype(font_path, 28)
fb = ImageFont.truetype(font_path, 29)
ft = ImageFont.truetype(font_path, 42)
fs = ImageFont.truetype(font_path, 23)
blue, pale, green, paleg, edge, text = "#5E8FCC", "#DDEBFA", "#72B45D", "#E0F0DC", "#727272", "#222222"

def box(x,y,w,h,label,kind="plain",bold=False):
    x,y,w,h = [v*S for v in (x,y,w,h)]
    fill, outline = ("#F7F7F7", edge)
    if kind == "core": fill, outline = pale, blue
    if kind == "result": fill, outline = paleg, green
    d.rounded_rectangle((x,y,x+w,y+h), radius=10*S, fill=fill, outline=outline, width=2*S)
    lines=label.split("\n"); ff=fb if bold else f
    heights=[d.textbbox((0,0),q,font=ff)[3] for q in lines]; total=sum(heights)+8*S*(len(lines)-1)
    yy=y+(h-total)/2
    for q,hh in zip(lines,heights):
        bb=d.textbbox((0,0),q,font=ff); d.text((x+w/2-(bb[2]-bb[0])/2,yy),q,font=ff,fill=text); yy+=hh+8*S

def line(points, arrow=True):
    pts=[(x*S,y*S) for x,y in points]; d.line(pts,fill=blue,width=2*S,joint="curve")
    if arrow:
        x,y=pts[-1]; px,py=pts[-2]; import math
        a=math.atan2(y-py,x-px); z=10*S
        p1=(x-z*math.cos(a-.55),y-z*math.sin(a-.55)); p2=(x-z*math.cos(a+.55),y-z*math.sin(a+.55))
        d.polygon([(x,y),p1,p2],fill=blue)

d.text((W/2-d.textbbox((0,0),"工作票与监控视频智能关联技术流程",font=ft)[2]/2,20),"工作票与监控视频智能关联技术流程",font=ft,fill=text)
tops=[(35,"电子工作票文本"),(205,"设备与作业点"),(375,"计划作业时段"),(545,"监控视频流"),(715,"摄像头点位信息")]
for x,t in tops: box(x,60,150,46,t)
box(48,150,220,66,"工作票语义解析\n提取人员、设备、地点、时间")
box(340,146,220,72,"多模态特征统一表征\n与实体标准化","core",True)
box(632,150,220,66,"视频帧采样与视觉分析\n人员、设备、行为特征提取")
box(315,264,270,72,"空间语义映射与时序同步\n候选视频片段检索","core",True)
box(315,380,270,70,"工单—视频多模态匹配\n置信度计算与精准关联")
box(355,490,190,58,"智能检索推理单元",bold=True)
box(55,590,300,58,"工单—视频关联数据库\n自动建立索引并持续更新","result")
box(545,590,300,58,"实时作业核查与历史回溯\n违规告警 · 证据片段精准调取","result")
for x,_ in tops: line([(x+75,106),(x+75,125),(450,125),(450,146)])
line([(268,183),(340,183)]); line([(632,183),(560,183)])
line([(450,218),(450,264)]); line([(450,336),(450,380)]); line([(450,450),(450,490)])
line([(450,548),(450,570),(205,570),(205,590)]); line([(450,548),(450,570),(695,570),(695,590)])
cap="时空一致性校验 · 语义相似度融合 · 视觉证据确认"; bb=d.textbbox((0,0),cap,font=fs); d.text((W/2-(bb[2]-bb[0])/2,690),cap,font=fs,fill="#666666")
im.save("work-ticket-video-association.png",dpi=(300,300))
