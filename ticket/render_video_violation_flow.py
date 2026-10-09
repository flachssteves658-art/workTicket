from PIL import Image, ImageDraw, ImageFont
import math

W,H,S=1800,2440,2
im=Image.new("RGB",(W,H),"white"); d=ImageDraw.Draw(im)
fp=r"C:\Windows\Fonts\msyh.ttc"
f=ImageFont.truetype(fp,27); fb=ImageFont.truetype(fp,29); ft=ImageFont.truetype(fp,42); fs=ImageFont.truetype(fp,22)
blue,pale,green,paleg,red,paler,gray,txt="#5E8FCC","#DDEBFA","#72B45D","#E0F0DC","#D36A61","#F7DFDC","#777777","#222222"

def box(x,y,w,h,label,kind="plain",bold=False):
    x,y,w,h=[v*S for v in (x,y,w,h)]; fill,ol="#F7F7F7",gray
    if kind=="core": fill,ol=pale,blue
    elif kind=="alert": fill,ol=paler,red
    elif kind=="result": fill,ol=paleg,green
    d.rounded_rectangle((x,y,x+w,y+h),radius=10*S,fill=fill,outline=ol,width=2*S)
    ff=fb if bold else f; lines=label.split("\n"); hs=[d.textbbox((0,0),q,font=ff)[3] for q in lines]; yy=y+(h-(sum(hs)+8*S*(len(lines)-1)))/2
    for q,hh in zip(lines,hs):
        bb=d.textbbox((0,0),q,font=ff); d.text((x+w/2-(bb[2]-bb[0])/2,yy),q,font=ff,fill=txt); yy+=hh+8*S

def line(points,color=blue,arrow=True,dash=False):
    pts=[(x*S,y*S) for x,y in points]
    if dash:
        for a,b in zip(pts[:-1],pts[1:]):
            dx,dy=b[0]-a[0],b[1]-a[1]; L=math.hypot(dx,dy); n=max(1,int(L/(14*S)))
            for i in range(0,n,2):
                p=i/n; q=min((i+1)/n,1); d.line((a[0]+dx*p,a[1]+dy*p,a[0]+dx*q,a[1]+dy*q),fill=color,width=2*S)
    else: d.line(pts,fill=color,width=2*S,joint="curve")
    if arrow:
        x,y=pts[-1]; px,py=pts[-2]; a=math.atan2(y-py,x-px); z=10*S
        d.polygon([(x,y),(x-z*math.cos(a-.55),y-z*math.sin(a-.55)),(x-z*math.cos(a+.55),y-z*math.sin(a+.55))],fill=color)

title="监控视频智能分析与违章行为识别流程"
bb=d.textbbox((0,0),title,font=ft); d.text((W/2-(bb[2]-bb[0])/2,18),title,font=ft,fill=txt)

tops=[(35,"现场监控摄像头"),(205,"实时视频流"),(375,"作业区域配置"),(545,"违章规则库"),(715,"人员与设备信息")]
for x,t in tops: box(x,60,150,46,t)
box(45,150,225,68,"视频接入与预处理\n解码、抽帧、去噪、增强")
box(337,146,226,76,"AI视觉特征提取\n目标检测与持续跟踪","core",True)
box(630,150,225,68,"场景与规则加载\n区域、时段、作业类型")

box(55,276,220,78,"人员行为识别\n越界、攀爬、跌倒、聚集")
box(340,276,220,78,"安全防护识别\n安全帽、安全带、工装")
box(625,276,220,78,"设备状态识别\n烟火、异物、车辆与机械")

box(310,407,280,76,"多目标时序行为分析\n轨迹关联与动作理解","core",True)
box(310,526,280,76,"规则引擎与风险判定\n对象 + 区域 + 行为 + 持续时间","core",True)
box(350,646,200,62,"是否构成违章？","alert",True)

box(65,764,280,72,"正常行为记录\n持续监测并更新目标状态","result")
box(555,764,280,72,"生成违章事件\n类型、位置、时间、风险等级","alert",True)
box(555,882,280,72,"告警推送与联动\n弹窗、声光、短信、平台消息","alert")
box(555,1000,280,72,"证据自动留存\n截图、前后视频、识别结果","core")
box(310,1124,280,72,"人工复核与闭环处置\n确认、派单、整改、销警","result",True)

for x,_ in tops: line([(x+75,106),(x+75,128),(450,128),(450,146)])
line([(270,184),(337,184)]); line([(630,184),(563,184)])
line([(450,222),(450,250),(165,250),(165,276)]); line([(450,222),(450,276)]); line([(450,222),(450,250),(735,250),(735,276)])
line([(165,354),(165,382),(450,382),(450,407)]); line([(450,354),(450,407)]); line([(735,354),(735,382),(450,382),(450,407)])
line([(450,483),(450,526)]); line([(450,602),(450,646)])
line([(350,677),(205,677),(205,764)],green); line([(550,677),(695,677),(695,764)],red)
line([(695,836),(695,882)],red); line([(695,954),(695,1000)]); line([(695,1072),(695,1100),(450,1100),(450,1124)])
line([(310,1160),(205,1160),(205,836)],blue,dash=True)

for x,y,t,c in [(285,660,"否",green),(615,660,"是",red),(260,1085,"模型持续学习 / 规则优化",gray)]:
    d.text((x*S,y*S),t,font=fs,fill=c)

im.save("video-violation-analysis-flow.png",dpi=(300,300))
