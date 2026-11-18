import AppKit
import QuartzCore
import UniformTypeIdentifiers

#if WHITEBOARD_PLUGIN
let isPluginRenderer = true
#else
let isPluginRenderer = false
#endif

struct Component: Codable, Equatable {
    var type: String
    var text: String? = nil
    var value: Double? = nil
}
struct Interaction: Codable, Equatable {
    var placeholder: String? = nil
    var choices: [String]? = nil
}
struct Scene: Codable, Equatable {
    var layout: String? = nil
    var motion: String? = nil
    var accent: String? = nil
    var decoration: String? = nil
}
struct Board: Codable {
    var directThread:String? = nil
    var followDelivery:String? = nil
    var followThread:String? = nil
    var followOffset:Int64? = nil
    var pageIndex:Int? = nil
    var pageCount:Int? = nil
    var pageID:String? = nil
    var canvas: CanvasSpec? = nil
    var writtenAt: Double? = nil
    var sceneSequence:Int? = nil
    var scene: Scene? = nil
    var turnID: String? = nil
    var interaction: Interaction? = nil
    var visualStyle: String? = nil
    var components: [Component]? = nil
    var title: String = "今天运动了吗？"
    var subtitle: String = ""
    var body: String = ""
    var items: [String] = []
    var endsAt: Double? = nil
    var startsAt: Double? = nil
    var showID: String = ""
    var action: String = "show"
}
extension Board {
    init(from decoder:Decoder) throws {
        self.init()
        let values=try decoder.container(keyedBy:CodingKeys.self)
        directThread=try values.decodeIfPresent(String.self,forKey:.directThread)
        followDelivery=try values.decodeIfPresent(String.self,forKey:.followDelivery)
        followOffset=try values.decodeIfPresent(Int64.self,forKey:.followOffset)
        followThread=try values.decodeIfPresent(String.self,forKey:.followThread)
        pageIndex=try values.decodeIfPresent(Int.self,forKey:.pageIndex)
        pageCount=try values.decodeIfPresent(Int.self,forKey:.pageCount)
        pageID=try values.decodeIfPresent(String.self,forKey:.pageID)
        canvas=try values.decodeIfPresent(CanvasSpec.self,forKey:.canvas)
        writtenAt=try values.decodeIfPresent(Double.self,forKey:.writtenAt)
        sceneSequence=try values.decodeIfPresent(Int.self,forKey:.sceneSequence)
        scene=try values.decodeIfPresent(Scene.self,forKey:.scene)
        turnID=try values.decodeIfPresent(String.self,forKey:.turnID)
        interaction=try values.decodeIfPresent(Interaction.self,forKey:.interaction)
        visualStyle=try values.decodeIfPresent(String.self,forKey:.visualStyle)
        components=try values.decodeIfPresent([Component].self,forKey:.components)
        title=try values.decodeIfPresent(String.self,forKey:.title) ?? title
        subtitle=try values.decodeIfPresent(String.self,forKey:.subtitle) ?? subtitle
        body=try values.decodeIfPresent(String.self,forKey:.body) ?? body
        items=try values.decodeIfPresent([String].self,forKey:.items) ?? items
        endsAt=try values.decodeIfPresent(Double.self,forKey:.endsAt)
        startsAt=try values.decodeIfPresent(Double.self,forKey:.startsAt)
        showID=try values.decodeIfPresent(String.self,forKey:.showID) ?? showID
        action=try values.decodeIfPresent(String.self,forKey:.action) ?? action
    }
}
final class WhiteboardApplication: NSApplication {
    var escape: (() -> Void)?
    override func sendEvent(_ event: NSEvent) {
        if event.type == .keyDown && event.keyCode == 53 { escape?(); return }
        super.sendEvent(event)
    }
}
final class BoardWindow: NSWindow {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { true }
}
final class ReplyButton: NSButton {
    var primary=false
    var hovering=false
    var tracking:NSTrackingArea?
    let ink=NSColor(srgbRed:0.29,green:0.15,blue:0.20,alpha:1)
    override init(frame:NSRect){super.init(frame:frame); setup()}
    required init?(coder:NSCoder){super.init(coder:coder);setup()}
    func setup(){isBordered=false;wantsLayer=true;layer?.cornerRadius=15;font = .systemFont(ofSize:16,weight:.medium)}
    override func updateTrackingAreas(){
        super.updateTrackingAreas();if let t=tracking{removeTrackingArea(t)}
        let t=NSTrackingArea(rect:bounds,options:[.mouseEnteredAndExited,.activeInKeyWindow,.inVisibleRect],owner:self);addTrackingArea(t);tracking=t;paint()
    }
    override func mouseEntered(with event:NSEvent){hovering=true;paint()}
    override func mouseExited(with event:NSEvent){hovering=false;paint()}
    override var isEnabled:Bool {didSet{paint()}}
    func paint(){
        let fill=primary ? ink : NSColor.white.withAlphaComponent(hovering ? 0.52 : 0.25)
        CATransaction.begin(); CATransaction.setAnimationDuration(0.14)
        layer?.backgroundColor=fill.cgColor;layer?.borderWidth=primary ? 0 : 1
        layer?.borderColor=ink.withAlphaComponent(hovering ? 0.24 : 0.10).cgColor
        CATransaction.commit()
        attributedTitle=NSAttributedString(string:title,attributes:[.font:font ?? NSFont.systemFont(ofSize:16),.foregroundColor:primary ? NSColor(srgbRed:1,green:0.95,blue:0.91,alpha:1) : ink])
    }
    override func mouseDown(with event:NSEvent){
        if !NSWorkspace.shared.accessibilityDisplayShouldReduceMotion {
            let a=CABasicAnimation(keyPath:"transform.scale");a.fromValue=1;a.toValue=0.97;a.duration=0.10;a.autoreverses=true;layer?.add(a,forKey:"press")
        }
        super.mouseDown(with:event)
    }
}
struct TimelineTrack: Codable, Equatable { var property:String;var keys:[[Double]];var easing:String? }
struct PathMarker: Codable, Equatable {var radius:Double;var color:String;var duration:Double}
struct CanvasNode: Codable, Equatable {
    var marker:PathMarker? = nil
    var type:String
    var id:String?
    var timeline:[TimelineTrack]?
    var text:String?;var x:Double?;var y:Double?;var w:Double?;var h:Double?;var size:Double?
    var weight:String?;var align:String?;var color:String?;var fill:String?;var motion:String?
    var delay:Double?;var duration:Double?;var points:[[Double]]?;var stroke:Double?;var effect:String?
}
struct CanvasSpec: Codable, Equatable {var nodes:[CanvasNode];var transition:String?}
final class DiagramView:NSView {
    var spec:CanvasSpec?
    var animated:[(CALayer,CanvasNode)]=[]
    func color(_ name:String?)->NSColor {
        if let name=name,name.count==7,name.first=="#",let rgb=UInt32(name.dropFirst(),radix:16){return NSColor(srgbRed:Double((rgb>>16)&255)/255,green:Double((rgb>>8)&255)/255,blue:Double(rgb&255)/255,alpha:1)}
        switch name {case "orange":return NSColor(srgbRed:0.9,green:0.36,blue:0.23,alpha:1)
        case "rose":return NSColor(srgbRed:0.68,green:0.24,blue:0.36,alpha:1)
        case "muted":return NSColor(srgbRed:0.55,green:0.47,blue:0.43,alpha:1)
        default:return NSColor(srgbRed:0.22,green:0.17,blue:0.17,alpha:1)}
    }
    var renderedSize=CGSize.zero
    var renderedSpec:CanvasSpec?
    func markPath(_ layer:CALayer,_ node:CanvasNode,animate:Bool) {
        guard let shape=layer as? CAShapeLayer else{return}
        let old=shape.sublayers?.first(where:{$0.name=="path-marker"})
        guard let marker=node.marker,let path=shape.path else{old?.removeFromSuperlayer();return}
        let dot=old ?? CALayer();dot.name="path-marker"
        CATransaction.begin();CATransaction.setDisableActions(true)
        dot.bounds=CGRect(x:0,y:0,width:2*marker.radius,height:2*marker.radius)
        dot.cornerRadius=marker.radius;dot.backgroundColor=color(marker.color).cgColor;dot.position=path.currentPoint
        if old==nil {shape.addSublayer(dot)}
        CATransaction.commit()
        guard animate,!NSWorkspace.shared.accessibilityDisplayShouldReduceMotion else{return}
        let travel=CAKeyframeAnimation(keyPath:"position");travel.path=path;travel.calculationMode = .paced
        travel.duration=marker.duration;travel.timingFunction=CAMediaTimingFunction(name:.easeInEaseOut)
        dot.add(travel,forKey:"travel")
    }
    func render(){
        renderedSize=bounds.size;renderedSpec=spec
        wantsLayer=true;subviews.forEach{$0.removeFromSuperview()};layer?.sublayers?.forEach{$0.removeFromSuperlayer()};animated=[]
        guard let spec=spec else{return};let W=bounds.width,H=bounds.height
        CATransaction.begin();CATransaction.setDisableActions(true)
        for n in spec.nodes.prefix(12){
            let x=max(0,min(1,n.x ?? 0)),y=max(0,min(1,n.y ?? 0))
            let w=max(0,min(1-x,n.w ?? 0.5)),h=max(0,min(1-y,n.h ?? 0.22))
            let frame=NSRect(x:x*W,y:(1-y-h)*H,width:w*W,height:h*H)
            if n.type=="text" {
                let label=NSTextField(labelWithString:n.text ?? "");label.wantsLayer=true
                label.alignment=n.align=="center" ? .center : (n.align=="right" ? .right : .left)
                label.lineBreakMode = .byClipping;label.maximumNumberOfLines=1
                let fontName=n.weight=="light" ? "PingFangSC-Light" : (n.weight=="semibold" ? "PingFangSC-Semibold" : "PingFangSC-Regular")
                let base=max(12,min((n.size ?? 0.16)*H,frame.height*0.8))
                let f=NSFont(name:fontName,size:base) ?? .systemFont(ofSize:base)
                let measure=((n.text ?? "") as NSString).size(withAttributes:[.font:f]).width
                let actual=base*min(1,max(1,frame.width-8)/max(1,measure))
                let font=NSFont(name:fontName,size:actual) ?? .systemFont(ofSize:actual)
                var attributes:[NSAttributedString.Key:Any]=[.font:font,.foregroundColor:color(n.color)]
                if n.effect=="outline"{attributes[.strokeWidth]=2;attributes[.strokeColor]=color(n.color)}
                if n.effect=="underline"{attributes[.underlineStyle]=NSUnderlineStyle.single.rawValue}
                let style=NSMutableParagraphStyle();style.alignment=label.alignment;attributes[.paragraphStyle]=style
                label.attributedStringValue=NSAttributedString(string:n.text ?? "",attributes:attributes)
                label.frame=frame;addSubview(label);if let l=label.layer{animated.append((l,n))}
            }else{
                let shape=CAShapeLayer();let path=CGMutablePath();shape.frame=bounds
                if n.type=="rect"{path.addRoundedRect(in:frame,cornerWidth:8,cornerHeight:8)}
                else if n.type=="circle"{path.addEllipse(in:frame)}
                else if let points=n.points,points.count>=2 {
                    let p=points.prefix(32).filter{$0.count==2}.map{CGPoint(x:$0[0]*W,y:(1-$0[1])*H)}
                    if let first=p.first{
                        path.move(to:first)
                        if n.type=="bezier",p.count>=4 {
                            for i in stride(from:1,to:p.count-2,by:3){path.addCurve(to:p[i+2],control1:p[i],control2:p[i+1])}
                        }else{p.dropFirst().forEach{path.addLine(to:$0)}}
                    }
                    if n.type=="arrow",p.count>=2{let a=p[p.count-2],b=p[p.count-1],angle=atan2(b.y-a.y,b.x-a.x),r=14.0
                        for delta in [-0.5,0.5]{path.move(to:b);path.addLine(to:CGPoint(x:b.x-r*cos(angle+delta),y:b.y-r*sin(angle+delta)))}}
                }
                shape.path=path;shape.strokeColor=n.color=="none" ? NSColor.clear.cgColor : color(n.color).cgColor;shape.lineWidth=min(10,max(1,n.stroke ?? 2));shape.lineCap = .round;shape.lineJoin = .round
                shape.fillColor=n.fill==nil || n.fill=="none" ? NSColor.clear.cgColor : color(n.fill).cgColor
                markPath(shape,n,animate:false);layer?.addSublayer(shape);animated.append((shape,n))
            }
        }
        CATransaction.commit()
    }
    func reconcile(_ next:CanvasSpec?){
        guard let next=next,let previous=spec,
              next.nodes.allSatisfy({$0.id != nil}),previous.nodes.allSatisfy({$0.id != nil}) else{
            spec=next;render();animate();return
        }
        let target=DiagramView(frame:bounds);target.spec=next;target.render()
        let old=Dictionary(uniqueKeysWithValues:animated.compactMap{ pair in pair.1.id.map{($0,pair)} })
        var kept:[(CALayer,CanvasNode)]=[]
        let reduced=NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
        for (fresh,n) in target.animated {
            guard let id=n.id else{continue}
            guard let (existing,before)=old[id],before.type==n.type else{
                if let view=target.subviews.first(where:{$0.layer===fresh}){view.removeFromSuperview();addSubview(view)}else{fresh.removeFromSuperlayer();layer?.addSublayer(fresh)}
                animateNodes([(fresh,n)]);kept.append((fresh,n));continue
            }
            if before==n{kept.append((existing,n));continue}
            let keys=existing is CAShapeLayer ? ["path","strokeColor","fillColor","lineWidth"] : ["position","bounds"]
            let shown=existing.presentation() ?? existing
            var from:[String:Any]=[:]
            for key in keys{from[key]=shown.value(forKeyPath:key)}
            CATransaction.begin();CATransaction.setDisableActions(true)
            if let label=subviews.first(where:{$0.layer===existing}) as? NSTextField,
               let replacement=target.subviews.first(where:{$0.layer===fresh}) as? NSTextField {
                label.attributedStringValue=replacement.attributedStringValue;label.alignment=replacement.alignment;label.frame=replacement.frame
            }else{for key in keys{existing.setValue(fresh.value(forKeyPath:key),forKeyPath:key)}}
            CATransaction.commit()
            if !reduced {
                for key in keys {
                    let a=CABasicAnimation(keyPath:key);a.fromValue=from[key];a.toValue=existing.value(forKeyPath:key);a.duration=min(2,max(0.1,n.duration ?? 0.45));a.timingFunction=CAMediaTimingFunction(name:.easeInEaseOut)
                    existing.add(a,forKey:"reconcile-"+key)
                }
            }
            if before.marker != n.marker || before.points != n.points {markPath(existing,n,animate:true)}
            for track in n.timeline ?? [] where !(before.timeline ?? []).contains(track) {
                guard let a=timelineAnimation(track),let key=a.keyPath,let final=a.values?.last else{continue}
                let current=(existing.presentation() ?? existing).value(forKeyPath:key)
                var values=a.values ?? [];if let current=current,!values.isEmpty{values[0]=current};a.values=values
                CATransaction.begin();CATransaction.setDisableActions(true);existing.setValue(final,forKeyPath:key);CATransaction.commit()
                if !reduced{a.beginTime=CACurrentMediaTime();existing.add(a,forKey:"timeline-"+track.property)}
            }
            kept.append((existing,n))
        }
        for (oldLayer,_) in animated where !kept.contains(where:{$0.0===oldLayer}){
            if let view=subviews.first(where:{$0.layer===oldLayer}){view.removeFromSuperview()}else{oldLayer.removeFromSuperlayer()}
        }
        spec=next;renderedSpec=next;animated=kept
    }
    func timelineAnimation(_ track:TimelineTrack)->CAKeyframeAnimation? {
        let paths=["x":"transform.translation.x","y":"transform.translation.y","scale":"transform.scale","rotation":"transform.rotation.z","opacity":"opacity","draw":"strokeEnd"]
        guard let path=paths[track.property],track.keys.count>=2,track.keys.count<=24,
              track.keys.allSatisfy({$0.count==2 && $0.allSatisfy{$0.isFinite}}),
              let end=track.keys.last?.first,end>0,end<=8 else{return nil}
        let a=CAKeyframeAnimation(keyPath:path)
        let multiplier=track.property=="x" ? bounds.width : (track.property=="y" ? -bounds.height : (track.property=="rotation" ? Double.pi/180 : 1))
        a.values=track.keys.map{NSNumber(value:$0[1]*multiplier)}
        a.keyTimes=track.keys.map{NSNumber(value:$0[0]/end)};a.duration=end
        let easing:CAMediaTimingFunctionName=track.easing=="linear" ? .linear : (track.easing=="ease-in" ? .easeIn : (track.easing=="ease-out" ? .easeOut : .easeInEaseOut))
        a.timingFunctions=Array(repeating:CAMediaTimingFunction(name:easing),count:track.keys.count-1)
        a.fillMode = .both;a.isRemovedOnCompletion=false
        return a
    }
    func animate(){animateNodes(animated)}
    func animateNodes(_ nodes:[(CALayer,CanvasNode)]){
        let reduced=NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
        for (layer,n) in nodes {
            markPath(layer,n,animate:true)
            if let tracks=n.timeline {
                for track in tracks {
                    guard let a=timelineAnimation(track),let final=a.values?.last,let key=a.keyPath else{continue}
                    CATransaction.begin();CATransaction.setDisableActions(true);layer.setValue(final,forKeyPath:key);CATransaction.commit()
                    if !reduced{a.beginTime=CACurrentMediaTime();layer.add(a,forKey:"timeline-"+track.property)}
                }
                continue
            }
            if reduced{continue}
            let mode=n.motion ?? "fade";if mode=="none"{continue}
            let fade=CABasicAnimation(keyPath:"opacity");fade.fromValue=0;fade.toValue=1
            var animations:[CAAnimation]=[fade]
            if mode=="draw",layer is CAShapeLayer {let draw=CABasicAnimation(keyPath:"strokeEnd");draw.fromValue=0;draw.toValue=1;animations.append(draw)}
            if mode=="rise" || mode=="slide"{let a=CABasicAnimation(keyPath:mode=="rise" ? "transform.translation.y" : "transform.translation.x");a.fromValue = -28;a.toValue=0;animations.append(a)}
            if mode=="pop"{let a=CABasicAnimation(keyPath:"transform.scale");a.fromValue=0.92;a.toValue=1;animations.append(a)}
            let a=CAAnimationGroup();a.animations=animations;a.duration=min(2,max(0.1,n.duration ?? 0.6));a.beginTime=CACurrentMediaTime()+min(1,max(0,n.delay ?? 0));a.fillMode = .backwards;a.timingFunction=CAMediaTimingFunction(controlPoints:0.22,1,0.36,1);layer.add(a,forKey:"node-entry")
        }
    }
}
// Each contour is a section of the same folded ribbon. Morph only when the conversation changes.
final class VoicePrint: NSView {
    enum Moment { case speaking, question, listening, waiting }
    private var contours: [CAShapeLayer] = []
    private var previousSize = CGSize.zero
    var moment: Moment = .speaking {
        didSet { if oldValue != moment { updatePaths(animated: true) } }
    }

    override init(frame: NSRect) {
        super.init(frame: frame)
        wantsLayer = true
        setAccessibilityElement(false)
        for i in 0..<58 {
            let u = CGFloat(i) / 57
            let stroke = CAShapeLayer()
            let orange = NSColor(srgbRed: 0.969, green: 0.318, blue: 0.235, alpha: 1)
            let pink = NSColor(srgbRed: 0.98, green: 0.44, blue: 0.67, alpha: 1)
            stroke.strokeColor = orange.blended(withFraction: u * u, of: pink)?.cgColor ?? orange.cgColor
            stroke.fillColor = nil
            stroke.lineCap = .round
            layer?.addSublayer(stroke)
            contours.append(stroke)
        }
    }
    required init?(coder: NSCoder) { fatalError() }
    override func hitTest(_ point: NSPoint) -> NSView? { nil }
    override func layout() {
        super.layout()
        if previousSize != bounds.size { previousSize = bounds.size; updatePaths(animated: false) }
    }
    private func updatePaths(animated: Bool) {
        guard bounds.width > 0, bounds.height > 0 else { return }
        let size = min(bounds.width, bounds.height)
        let phase: CGFloat
        switch moment {
        case .question: phase = 0.65
        case .speaking: phase = -0.22
        case .listening: phase = 1.45
        case .waiting: phase = 2.05
        }
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        for (i, stroke) in contours.enumerated() {
            let u = CGFloat(i) / CGFloat(contours.count - 1)
            let path = CGMutablePath()
            for j in 0...96 {
                let t = CGFloat(j) * .pi * 2 / 96
                let twist = 0.35 * sin(2*t + phase) + 0.72*u
                let radius = 0.30 + 0.048*cos(3*t - phase + 1.6*u) + 0.04*sin(t + 3*u)
                let x = (radius * cos(t + twist) + (u-0.5)*0.26) * size
                let y = (radius * sin(t) * (0.72+0.33*u) + (u-0.5)*0.16 + 0.085*cos(2*t+phase+3*u)) * size
                let point = CGPoint(x: bounds.midX + x*0.95 - y*0.30, y: bounds.midY + y*0.95 + x*0.30)
                if j==0 { path.move(to: point) } else { path.addLine(to: point) }
            }
            path.closeSubpath()
            if animated, !NSWorkspace.shared.accessibilityDisplayShouldReduceMotion, let old = stroke.presentation()?.path ?? stroke.path {
                let move = CABasicAnimation(keyPath: "path")
                move.fromValue = old; move.toValue = path; move.duration = 0.48
                move.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
                stroke.add(move, forKey: "response")
            }
            stroke.lineWidth = max(0.8, size/390)
            stroke.path = path
        }
        CATransaction.commit()
    }
}

final class Canvas: NSView, NSTextFieldDelegate {
    let group=NSView()
    let voicePrint = VoicePrint(frame: .zero)
    let paper = CAGradientLayer()
    var liveSide: Bool { board.visualStyle == "live-side" }
    var editorialHeadline: Bool { liveSide || (board.canvas == nil && board.scene?.layout != "countdown") }
    let liveLead=NSTextField(labelWithString:"")
    var onBeginInput:(()->Void)?
    var editStatus:((Bool)->Void)?
    func controlTextDidBeginEditing(_ obj:Notification){editStatus?(true);voicePrint.moment = .listening;onBeginInput?()}
    func controlTextDidEndEditing(_ obj:Notification){editStatus?(false);updateVoice()}
    func updateVoice(){
        voicePrint.moment = submitted ? .waiting : (board.title.hasSuffix("？") || board.title.hasSuffix("?") ? .question : .speaking)
    }
    func previewClause(_ text:String){
        liveLead.stringValue=text;fit(liveLead,"PingFangSC-Light",min(150,bounds.height*0.17),liveLead.frame.width)
        group.isHidden=true;liveLead.isHidden=false
        enter(liveLead,-12,0)
    }
    let diagram=DiagramView()
    var onSettled:((String)->Void)?
    let first=NSTextField(labelWithString:"")
    let second=NSTextField(labelWithString:"")
    let brand=NSTextField(labelWithString:"dot / 对话")
    let input=NSTextField(string:"")
    let send=ReplyButton(title:"↵",target:nil,action:nil)
    let receipt=NSTextField(labelWithString:"")
    let feedback=NSTextField(labelWithString:"")
    let clock=NSTextField(labelWithString:"")
    let previous=NSButton(title:"‹",target:nil,action:nil),next=NSButton(title:"›",target:nil,action:nil)
    let pageNumber=NSTextField(labelWithString:"")
    let openFile=NSPopUpButton(frame:.zero,pullsDown:true)
    var saveFile:(()->Void)?
    var newConversation:((Bool)->Void)?
    var navigate:((Int)->Void)?
    var chooseFile:(()->Void)?
    let mode=NSPopUpButton(frame:.zero,pullsDown:false)
    let retry=ReplyButton(title:"重试",target:nil,action:nil)
    let mark=CAShapeLayer()
    var modeChanged:((Bool)->Void)?
    var retryReply:(()->Void)?
    var didSubmit:(()->Void)?
    var daily=false
    let exitButton=NSButton(title:"esc",target:nil,action:nil)
    let ornament=CAShapeLayer()
    let topRule=CALayer(),rule=CAShapeLayer(),inputRule=CALayer(),progress=CALayer()
    var choices:[NSButton]=[]
    var quit:(()->Void)?
    var onReply:((String?)->Bool)?
    var continued=false
    var advance:(()->Void)?
    var board=Board(),revision=0,submitted=false,appeared=false
    let ink=NSColor(srgbRed:0.22,green:0.17,blue:0.17,alpha:1)
    let orange=NSColor(srgbRed:0.90,green:0.36,blue:0.23,alpha:1)
    override var acceptsFirstResponder:Bool{true}
    override init(frame:NSRect){
        super.init(frame:frame);appearance=NSAppearance(named:.aqua);wantsLayer=true;layer?.backgroundColor=NSColor(srgbRed:0.973,green:0.898,blue:0.871,alpha:1).cgColor
        paper.colors=[NSColor(srgbRed:0.991,green:0.984,blue:0.967,alpha:1).cgColor,
                      NSColor(srgbRed:0.985,green:0.962,blue:0.927,alpha:1).cgColor]
        paper.startPoint=CGPoint(x:0,y:0.8);paper.endPoint=CGPoint(x:1,y:0.2)
        layer?.insertSublayer(paper,at:0)
        group.wantsLayer=true;addSubview(group);group.addSubview(voicePrint);group.addSubview(diagram)
        for label in [first,second]{label.wantsLayer=true;label.alignment = .left;label.lineBreakMode = .byClipping;label.maximumNumberOfLines=1;group.addSubview(label)}
        liveLead.wantsLayer=true;liveLead.textColor=ink;liveLead.isHidden=true;addSubview(liveLead)
        first.textColor=ink;second.textColor=orange
        for label in [brand,receipt,feedback,clock]{label.wantsLayer=true;label.textColor=ink;addSubview(label)}
        mark.fillColor=diagram.color("#F7513C").cgColor;layer?.addSublayer(mark)
        for (b,title,action) in [(previous,"上一页",#selector(goBack)),(next,"下一页",#selector(goNext))] {
            b.isBordered=false;b.target=self;b.action=action;b.setAccessibilityLabel(title);b.contentTintColor=ink;addSubview(b)
        }
        openFile.addItems(withTitles:["文稿","打开文稿…","保存当前文稿…","独立模型对话","每日锻炼","回到 Dot 聊天"])
        if isPluginRenderer {
            openFile.menu?.item(at:3)?.isHidden=true
            openFile.menu?.item(at:4)?.isHidden=true
        }
        openFile.isBordered=false;openFile.target=self;openFile.action=#selector(fileAction);openFile.setAccessibilityLabel("文稿");addSubview(openFile)
        pageNumber.alignment = .center;pageNumber.font = .monospacedDigitSystemFont(ofSize:13,weight:.medium);pageNumber.textColor=ink;addSubview(pageNumber)
        mode.addItems(withTitles:["Codex","DeepSeek Flash","本地演示"]);mode.isBordered=false
        mode.font = .systemFont(ofSize:14,weight:.medium);mode.target=self;mode.action=#selector(selectMode)
        mode.setAccessibilityLabel("对话模式");mode.isHidden=true;addSubview(mode)
        retry.isHidden=true;retry.target=self;retry.action=#selector(retryAction);retry.paint();addSubview(retry)
        brand.font = .systemFont(ofSize:18,weight:.medium)
        receipt.font = .systemFont(ofSize:32,weight:.light);receipt.isHidden=true
        feedback.font = .systemFont(ofSize:12);feedback.textColor=ink.withAlphaComponent(0.6)
        clock.font = .monospacedDigitSystemFont(ofSize:18,weight:.light)
        for line in [topRule,inputRule]{line.backgroundColor=ink.withAlphaComponent(0.25).cgColor;layer?.addSublayer(line)}
        rule.strokeColor=orange.cgColor;rule.fillColor=NSColor.clear.cgColor;rule.lineWidth=2;layer?.addSublayer(rule)
        progress.backgroundColor=orange.cgColor;layer?.addSublayer(progress)
        ornament.fillColor=NSColor.clear.cgColor;ornament.strokeColor=orange.withAlphaComponent(0.16).cgColor;ornament.lineWidth=2;ornament.lineCap = .round;layer?.insertSublayer(ornament,below:group.layer)
        input.delegate=self;(input.cell as? NSTextFieldCell)?.sendsActionOnEndEditing=false;input.isEditable=true;input.isSelectable=true;input.isBordered=false;input.drawsBackground=false
        input.font = .systemFont(ofSize:20,weight:.regular);input.textColor=ink;input.focusRingType = .default
        input.wantsLayer=true;input.target=self;input.action=#selector(sendReply);input.setAccessibilityLabel("回复白板");addSubview(input)
        send.primary=true;send.target=self;send.action=#selector(sendReply);send.setAccessibilityLabel("发送回复");send.paint();addSubview(send)
        exitButton.isBordered=false;exitButton.font = .systemFont(ofSize:16);exitButton.contentTintColor=ink.withAlphaComponent(0.65)
        exitButton.target=self;exitButton.action=#selector(exitNow);exitButton.setAccessibilityLabel("退出白板");addSubview(exitButton)
    }
    required init?(coder:NSCoder){fatalError()}
    @objc func goBack(){navigate?(-1)}
    @objc func goNext(){advance?()}
    @objc func fileAction(){
        switch openFile.indexOfSelectedItem {case 1:chooseFile?();case 2:saveFile?();case 3:newConversation?(false);case 4:newConversation?(true);case 5:returnToChat();default:break}
    }
    func returnToChat(){
        if let url=URL(string:"https://chatgpt.com/dots"), NSWorkspace.shared.open(url) {quit?();return}
        feedback.stringValue="请在 ChatGPT 中打开个人 dot 的主对话"
    }
    func navigationChrome(){
        let count=board.pageCount ?? 0,index=board.pageIndex ?? 0
        next.title=editorialHeadline && !daily && count<2 ? "继续 →" : "›"
        for v in [previous,pageNumber] {v.isHidden=count<2}
        next.isHidden=count<2 && board.interaction==nil
        next.toolTip="继续到下一页（跳过当前问题）";previous.isEnabled=index>0;next.isEnabled=index+1<count || (board.interaction != nil && !submitted);pageNumber.stringValue="\(index+1) / \(count)"
        openFile.isHidden = !daily && count==0
        openFile.menu?.item(at:2)?.isEnabled=board.pageID != nil
    }
    @objc func selectMode(){modeChanged?(mode.indexOfSelectedItem==0)}
    @objc func retryAction(){retryReply?()}
    @objc func exitNow(){quit?()}
    override func keyDown(with event:NSEvent){if event.keyCode==53{quit?()}else{super.keyDown(with:event)}}
    override func cancelOperation(_ sender:Any?){quit?()}
    func lines(_ text:String)->(String,String){
        let t=text.trimmingCharacters(in:.whitespacesAndNewlines)
        if let p=t.firstIndex(of:"\n"){return(String(t[..<p]),String(t[t.index(after:p)...]).replacingOccurrences(of:"\n",with:" "))}
        let chars=Array(t)
        if chars.count<=4{return("",t)}
        for (i,c) in chars.enumerated() where "，,：:；;".contains(c) && i>0 && i<chars.count-1{return(String(chars[0...i]),String(chars[(i+1)...]))}
        let split=max(1,chars.count/2);return(String(chars[..<split]),String(chars[split...]))
    }
    func replaceChoices(_ values:[String]){
        guard choices.map({$0.title}) != values else{return}
        choices.forEach{$0.removeFromSuperview()};choices=[]
        for (i,text) in values.enumerated(){
            let b=ReplyButton(title:text,target:self,action:#selector(choose(_:)));b.primary=i==0;b.paint();addSubview(b);choices.append(b)
        }
        needsLayout=true
    }
    func configure(keepDraft:Bool){
        group.isHidden=false;liveLead.isHidden=true;submitted=false;continued=false;receipt.isHidden=true;retry.isHidden=true;receipt.alphaValue=1
        mode.isHidden = !daily
        navigationChrome()
        brand.stringValue=(daily || board.pageID != nil) ? board.subtitle : (board.subtitle.hasPrefix("模拟") ? board.subtitle : "dot   /   对话")
        let active=board.interaction != nil
        for v in [input,send]{v.isHidden = !active;v.alphaValue=1};feedback.isHidden=false;feedback.alphaValue=1;inputRule.isHidden = !active
        if !keepDraft {input.stringValue=""};input.isEnabled=true;send.isEnabled=true
        input.placeholderAttributedString=NSAttributedString(string:board.interaction?.placeholder ?? "说说你的想法",attributes:[.foregroundColor:ink.withAlphaComponent(0.45),.font:NSFont.systemFont(ofSize:24,weight:.light)])
        feedback.stringValue="空格继续 · Enter 回答 · Esc 退出"
        if !active {feedback.stringValue="空格下一页 · Esc 退出"}
        replaceChoices(board.interaction?.choices ?? [])
        for button in choices { button.isEnabled=true;button.alphaValue=1 }
        let title=board.components?.first(where:{$0.type=="headline"})?.text ?? (board.title.isEmpty ? board.body : board.title)
        let pair=editorialHeadline || board.scene?.layout == "countdown" ? ("",title) : lines(title)
        first.stringValue=pair.0;second.stringValue=pair.1
        second.textColor=board.scene?.accent == "ink" ? ink : (board.scene?.accent == "rose" ? NSColor(srgbRed:0.68,green:0.24,blue:0.36,alpha:1) : orange)
        rule.strokeColor=second.textColor?.cgColor
        diagram.spec=board.canvas;diagram.isHidden=board.canvas==nil;first.isHidden=board.canvas != nil;second.isHidden=board.canvas != nil && !liveSide
        voicePrint.isHidden = !editorialHeadline || liveSide
        if editorialHeadline {
            second.textColor=ink
            second.maximumNumberOfLines=3;second.lineBreakMode = .byWordWrapping
            second.cell?.wraps=true;second.cell?.isScrollable=false
        } else {
            second.maximumNumberOfLines=1;second.lineBreakMode = .byClipping;second.cell?.wraps=false
        }
        updateVoice();needsLayout=true;layoutSubtreeIfNeeded();tick()
    }
    func setBoard(_ new:Board){
        if appeared && new.action=="patch" {
            guard new.showID==board.showID,new.turnID==board.turnID,!submitted,
                  new.sceneSequence == nil || (new.sceneSequence ?? 0) > (board.sceneSequence ?? 0) else{return}
            board=new;diagram.isHidden=new.canvas==nil
            first.isHidden=new.canvas != nil;second.isHidden=new.canvas != nil && !liveSide
            diagram.reconcile(new.canvas);if new.canvas==nil {first.isHidden=false;second.isHidden=false};return
        }
        let changed=new.canvas != board.canvas || new.turnID != board.turnID || new.showID != board.showID || new.title != board.title || new.components != board.components || new.interaction != board.interaction || new.scene != board.scene
        let keepDraft=appeared && (!submitted || continued) && (!input.stringValue.isEmpty || input.currentEditor() != nil)
        let previouslyVisible=appeared
        board=new;guard changed || !appeared else{tick();return}
        revision+=1
        if previouslyVisible && !NSWorkspace.shared.accessibilityDisplayShouldReduceMotion && new.canvas?.transition != "cut" {
            let slide=CATransition()
            slide.type=new.canvas?.transition=="push" ? .push : .fade;slide.subtype = .fromRight
            slide.duration=new.canvas?.transition=="push" ? 0.34 : 0.19
            slide.timingFunction=CAMediaTimingFunction(name:.easeOut);group.layer?.add(slide,forKey:"page")
        }
        configure(keepDraft:keepDraft);arrive();appeared=true
    }
    func fit(_ label:NSTextField,_ font:String,_ base:CGFloat,_ width:CGFloat){
        let initial=NSFont(name:font,size:base) ?? .systemFont(ofSize:base)
        let measured=(label.stringValue as NSString).size(withAttributes:[.font:initial]).width
        let size=measured>width-12 ? base*(width-12)/max(1,measured) : base
        label.font=NSFont(name:font,size:size) ?? .systemFont(ofSize:size)
    }
    override func layout(){
        super.layout();let w=bounds.width,h=bounds.height,s=min(w/1440,h/900),margin=w*0.09
        CATransaction.begin();CATransaction.setDisableActions(true);paper.frame=bounds;CATransaction.commit()
        liveLead.frame=NSRect(x:margin,y:h*0.43,width:w*0.82,height:h*0.30)
        group.frame=bounds
        let reading=board.pageID != nil && board.interaction==nil
        if liveSide && board.canvas != nil {
            diagram.frame=w<640 ? NSRect(x:w*0.12,y:h*0.46,width:w*0.76,height:h*0.19) : NSRect(x:w*0.55,y:h*0.29,width:w*0.38,height:h*0.48)
        } else {
            diagram.frame=NSRect(x:w*0.09,y:h*(reading ? 0.13:0.30),width:w*0.82,height:h*(reading ? 0.65:0.51))
        }
        rule.isHidden=reading
        if diagram.renderedSize != diagram.bounds.size || diagram.renderedSpec != diagram.spec {diagram.render()}
        brand.frame=NSRect(x:margin+24,y:h*0.89,width:300,height:30)
        mark.path=CGPath(ellipseIn:NSRect(x:margin,y:h*0.89+10,width:13,height:13),transform:nil)
        previous.frame=NSRect(x:w*0.5-76,y:h*0.89,width:35,height:30);next.frame=NSRect(x:w*0.5+40,y:h*0.89,width:35,height:30)
        pageNumber.frame=NSRect(x:w*0.5-39,y:h*0.89+5,width:78,height:22)
        openFile.frame=NSRect(x:w-margin-(daily ? 255:138),y:h*0.89,width:75,height:27)
        mode.frame=NSRect(x:w-margin-172,y:h*0.89+2,width:132,height:27)
        retry.frame=NSRect(x:w*0.70,y:h*0.13,width:90,height:44)
        exitButton.frame=NSRect(x:w-margin-50,y:h*0.89,width:50,height:28)
        CATransaction.begin();CATransaction.setDisableActions(true)
        topRule.frame=NSRect(x:margin,y:h*0.865,width:w-2*margin,height:1)
        let path=CGMutablePath();path.move(to:CGPoint(x:margin,y:h*0.272));path.addLine(to:CGPoint(x:w-margin,y:h*0.272));rule.path=path
        inputRule.frame=NSRect(x:margin,y:h*0.116,width:w*0.51,height:1)
        let decoration=CGMutablePath(),cx=w*0.87,cy=h*0.77,r=min(w,h)*0.065
        if board.scene?.decoration == "rings" {
            for factor in [0.6,1.0,1.4]{decoration.addArc(center:CGPoint(x:cx,y:cy),radius:r*factor,startAngle:0.15,endAngle:Double.pi*1.7,clockwise:false)}
        }else if board.scene?.decoration == "strides"{
            for i in 0..<4{let x=cx-40+Double(i)*22;decoration.move(to:CGPoint(x:x,y:cy-r*0.5));decoration.addLine(to:CGPoint(x:x+32,y:cy+r*0.5))}
        }
        ornament.path=decoration;ornament.isHidden=board.scene?.decoration==nil || board.scene?.decoration=="none"
        CATransaction.commit()
        if first.stringValue.isEmpty{
            second.frame=NSRect(x:margin,y:h*0.38,width:w*0.82,height:h*0.38);second.alignment = board.scene?.layout == "focus" || board.scene?.layout == "countdown" ? .center : .left;fit(second,"PingFangSC-Semibold",220*s,second.frame.width)
            first.frame = .zero
        }else{
            second.alignment = .left
            first.frame=NSRect(x:margin,y:h*0.54,width:w*0.82,height:h*0.30);fit(first,"PingFangSC-Light",170*s,first.frame.width)
            second.frame=NSRect(x:w*0.195,y:h*0.30,width:w*0.715,height:h*0.34);fit(second,"PingFangSC-Semibold",190*s,second.frame.width)
        }
        let iy=h*0.13
        input.frame=NSRect(x:margin,y:iy,width:w*0.51-68,height:44)
        send.frame=NSRect(x:margin+w*0.51-52,y:iy-4,width:48,height:44)
        receipt.frame=NSRect(x:margin,y:iy,width:w*0.82,height:54)
        receipt.lineBreakMode = .byTruncatingTail
        feedback.frame=NSRect(x:margin,y:h*0.068,width:w*0.75,height:22)
        let n=max(1,choices.count),gap:CGFloat=8
        let available=w*0.355
        let font=NSFont.systemFont(ofSize:max(12,min(20*s,17)),weight:.medium)
        let widths=choices.map { min((available-CGFloat(n-1)*gap)/CGFloat(n),max(65,($0.title as NSString).size(withAttributes:[.font:font]).width+28)) }
        var cursor=w-margin-widths.reduce(0,+)-CGFloat(n-1)*gap
        for (i,b) in choices.enumerated(){
            b.frame=NSRect(x:cursor,y:iy-4,width:widths[i],height:44);b.font=font
            if let button=b as? ReplyButton {button.layer?.cornerRadius=22;button.paint()}
            b.toolTip=b.title;cursor+=widths[i]+gap
        }
        if board.scene?.layout == "countdown" {
            clock.frame=NSRect(x:margin,y:h*0.30,width:w*0.82,height:80*s);clock.font = .monospacedDigitSystemFont(ofSize:60*s,weight:.light);clock.alignment = .center
        }else{clock.frame=NSRect(x:w-margin-180,y:h*0.23,width:180,height:28);clock.font = .monospacedDigitSystemFont(ofSize:18,weight:.light);clock.alignment = .right}
        if board.endsAt==nil && !board.body.isEmpty{clock.frame=NSRect(x:margin,y:h*0.23,width:w*0.82,height:30);clock.alignment = .left}
        progress.frame=NSRect(x:margin,y:h*0.272,width:0,height:2)
        if editorialHeadline {
            let edge=max(26,w*0.075), headerY=h-max(48,h*0.085), compact=w<640
            let area=compact ? w-2*edge : (liveSide && board.canvas==nil ? w*0.79:w*0.50)
            let isQuestion=board.title.hasSuffix("？") || board.title.hasSuffix("?")
            var points=max(30,min(94,w*(compact ? 0.085:0.062),h*0.112))
            let maxHeight=h*(compact ? 0.28:0.39)
            let face=isQuestion ? "STSongti-SC-Bold" : "PingFangSC-Medium"
            var measured:CGFloat=0
            repeat {
                second.font=NSFont(name:face,size:points) ?? NSFont.systemFont(ofSize:points,weight:.medium)
                measured=ceil((second.stringValue as NSString).boundingRect(with:NSSize(width:area-8,height:10000),options:[.usesLineFragmentOrigin,.usesFontLeading],attributes:[.font:second.font!]).height)
                if measured<=maxHeight || points<=25 {break};points-=2
            } while true
            let center=h*(compact ? (liveSide && board.canvas != nil ? 0.76:0.62):0.55), textHeight=min(maxHeight,measured+10)
            second.alignment = .left
            second.frame=NSRect(x:edge,y:center-textHeight/2,width:area,height:textHeight)
            first.frame = .zero
            voicePrint.frame = compact ? NSRect(x:w*0.47,y:h*0.68,width:w*0.43,height:h*0.18) : NSRect(x:w*0.53,y:h*0.255,width:w*0.415,height:h*0.59)
            liveLead.frame=second.frame
            brand.frame=NSRect(x:edge+22,y:headerY,width:min(260,w*0.32),height:23)
            brand.font = .systemFont(ofSize:14,weight:.medium)
            mark.path=CGPath(ellipseIn:NSRect(x:edge,y:headerY+7,width:10,height:10),transform:nil)
            for control in [previous,next,exitButton] {control.frame.origin.y=headerY-3}
            pageNumber.frame.origin.y=headerY+1
            openFile.frame.origin.y=headerY-3;mode.frame.origin.y=headerY-2
            if !daily && (board.pageCount ?? 0)<2 {
                next.frame=NSRect(x:w-edge-218,y:headerY-3,width:68,height:27)
            }
            if daily && compact {brand.frame.size.width=min(105,w*0.22)}
            ornament.isHidden=true;rule.isHidden=true
            CATransaction.begin();CATransaction.setDisableActions(true)
            topRule.frame=NSRect(x:edge,y:h*0.235,width:w-edge*2,height:1)
            topRule.backgroundColor=ink.withAlphaComponent(0.17).cgColor
            inputRule.frame=NSRect(x:edge,y:h*0.088,width:compact ? w-edge*2:w*0.46,height:1)
            inputRule.backgroundColor=ink.withAlphaComponent(0.24).cgColor
            CATransaction.commit()
            let fieldY=h*0.10, fieldWidth=compact ? w-edge*2:w*0.46
            input.frame=NSRect(x:edge,y:fieldY,width:fieldWidth-58,height:31)
            send.frame=NSRect(x:edge+fieldWidth-41,y:fieldY-3,width:40,height:34)
            send.layer?.cornerRadius=17
            receipt.frame=NSRect(x:edge,y:fieldY,width:w-edge*2,height:44)
            feedback.frame=NSRect(x:edge,y:h*0.034,width:w-edge*2,height:20)
            if compact {for b in choices {b.frame.origin.y=h*0.168}}
            if board.endsAt==nil && !board.body.isEmpty {clock.frame=NSRect(x:edge,y:h*0.255,width:w-2*edge,height:25)}
        }
    }
    func enter(_ view:NSView,_ dx:Double,_ delay:Double){
        view.alphaValue=1;guard !NSWorkspace.shared.accessibilityDisplayShouldReduceMotion && board.scene?.motion != "quiet" else{return}
        let fade=CABasicAnimation(keyPath:"opacity");fade.fromValue=0;fade.toValue=1
        let mode=board.scene?.motion ?? "slide"
        let slide=CABasicAnimation(keyPath:"transform.translation.x");slide.fromValue=mode == "rise" || mode == "pop" || mode == "breathe" ? 0 : (mode == "sweep" ? dx*2 : dx);slide.toValue=0
        let rise=CABasicAnimation(keyPath:"transform.translation.y");rise.fromValue = mode == "rise" ? -36 : -12;rise.toValue=0
        let scale=CAKeyframeAnimation(keyPath:"transform.scale")
        scale.values=mode == "pop" ? [0.92,1.015,1] : (mode == "breathe" ? [0.98,1.025,1] : [1,1,1]);scale.keyTimes=[0,0.7,1]
        let a=CAAnimationGroup();a.animations=[fade,slide,rise,scale];a.duration=mode == "breathe" ? 1.6 : 0.72;a.beginTime=CACurrentMediaTime()+delay;a.fillMode = .backwards
        a.timingFunction=CAMediaTimingFunction(controlPoints:0.22,1,0.36,1);view.layer?.add(a,forKey:"editorial-enter")
    }
    func arrive(){
        group.alphaValue=1
        if editorialHeadline && !liveSide {enter(voicePrint,14,0)}
        if liveSide && board.canvas != nil {enter(second,-18,0)}
        if board.canvas != nil{diagram.animate();if board.canvas?.transition=="lift"{enter(diagram,0,0)}}else{enter(first,-45,0);enter(second,55,0.15)}
        let turn=board.turnID ?? ""
        var duration=0.9
        for node in board.canvas?.nodes ?? [] {
            let ends:[Double]=node.timeline?.compactMap{ track in track.keys.last?.first } ?? []
            duration=max(duration,node.marker?.duration ?? 0);duration=max(duration,ends.max() ?? ((node.delay ?? 0)+(node.duration ?? 0.6)))
        }
        DispatchQueue.main.asyncAfter(deadline:.now()+(NSWorkspace.shared.accessibilityDisplayShouldReduceMotion ? 0 : max(0.9,duration))){[weak self] in guard self?.board.turnID==turn else{return};self?.onSettled?(turn)}
        if !NSWorkspace.shared.accessibilityDisplayShouldReduceMotion && board.scene?.motion != "quiet"{
            let decor=CABasicAnimation(keyPath:"strokeEnd");decor.fromValue=0;decor.toValue=1;decor.duration=1.2;ornament.add(decor,forKey:"ornament-draw")
            let a=CABasicAnimation(keyPath:"strokeEnd");a.fromValue=0;a.toValue=1;a.duration=0.8;a.beginTime=CACurrentMediaTime()+0.3;a.fillMode = .backwards;rule.add(a,forKey:"rule-enter")
        }
        if !daily {for v in [input,send,feedback]{enter(v,0,0.18)}}
        for (i,b) in choices.enumerated(){enter(b,0,0.05+Double(i)*0.04)}
    }
    @objc func sendReply(){submit(input.stringValue)}
    @objc func choose(_ sender:NSButton){submit(sender.title)}
    func submit(_ raw:String){
        let text=raw.trimmingCharacters(in:.whitespacesAndNewlines)
        guard !submitted,board.interaction != nil else{return}
        guard !text.isEmpty else{feedback.stringValue="写一句，或选一个回答";return}
        guard text.count<=2000 else{feedback.stringValue="超过 2000 字，请缩短后重试";return}
        finishTurn(text)
    }
    func finishTurn(_ answer:String?){
        guard !submitted,board.interaction != nil else{return}
        guard onReply?(answer)==true else{feedback.stringValue="页面已改变，请重试";return}
        continued=answer==nil
        submitted=true;updateVoice();input.isEnabled=false;send.isEnabled=false;choices.forEach{$0.isEnabled=false}
        input.layer?.removeAnimation(forKey:"editorial-enter");receipt.stringValue=answer ?? "";receipt.isHidden=continued;feedback.stringValue=daily ? (mode.indexOfSelectedItem==2 ? "正在翻页…" : "正在生成下一句…") : (continued ? "等待下一句…" : "已收到 · 等待 Dot 读取")
        NSAnimationContext.runAnimationGroup({c in c.duration=NSWorkspace.shared.accessibilityDisplayShouldReduceMotion ? 0 : 0.22;self.input.animator().alphaValue=0;self.send.animator().alphaValue=0;self.choices.forEach{$0.animator().alphaValue=0};self.group.animator().alphaValue=0.65})
        receipt.alphaValue=1;CATransaction.flush();didSubmit?()
    }
    func tick(){
        if let end=board.endsAt{let left=max(0,Int(ceil(end-Date().timeIntervalSince1970)));clock.stringValue=left==0 ? "时间到" : String(format:"%02d:%02d",left/60,left%60)}else{clock.stringValue=board.body}
        let explicit=board.components?.first(where:{$0.type=="progress"})?.value
        var value=explicit ?? 0
        if explicit==nil,let start=board.startsAt,let end=board.endsAt,end>start{value=(Date().timeIntervalSince1970-start)/(end-start)}
        CATransaction.begin();CATransaction.setDisableActions(true);progress.frame.size.width=bounds.width*0.82*min(1,max(0,value));CATransaction.commit()
    }
}
final class Delegate: NSObject, NSApplicationDelegate {
    var window: BoardWindow!
    var canvas: Canvas!
    var ticker: Timer?
    var watcher: DispatchSourceFileSystemObject?
    var watchFD:Int32 = -1
    var bytes: Data?
    var board=Board()
    var editing=false
    var observedAt:Double=0
    var committedAt:Double=0
    var settledAt:Double?
    let testWindow=CommandLine.arguments.contains("--test-window") && ProcessInfo.processInfo.environment["DOT_WHITEBOARD_DATA"] != nil
    var closing=false
    var daily=false
    var exercise=ExercisePage.opening
    let bridge=WhiteboardModelBridge()
    var exerciseMode=false
    var credential=""
    var pageIDs:[String]=[]
    var drafts:[String:String]=[:]
    var request:String?
    var lastAnswer:String?
    var lastQuestion=""
    var history:[[String:String]]=[]
    var receivedHeadline=false
    var metrics:[String:Double]=[:]
    var timeout:DispatchWorkItem?
    var idleRelease:DispatchWorkItem?
    var escapeMonitor:Any?
    var testKeys:[DispatchSourceSignal]=[]
    var follower:Process?
    var now:Double {Date().timeIntervalSince1970}
    func showExercise(_ page:ExercisePage, first:Bool=false) {
        exercise=page
        var next=Board()
        next.showID=first ? UUID().uuidString : board.showID
        next.turnID=UUID().uuidString;next.title=page.title.replacingOccurrences(of:"|",with:"")
        next.subtitle=exerciseMode ? "dot   /   每日锻炼" : "动态白板"
        next.canvas=exerciseMode ? page.canvas : page.custom
        if !exerciseMode {next.title=page.title.replacingOccurrences(of:"|",with:"\n")}
        next.interaction=Interaction(placeholder:first && !exerciseMode ? "说说你正在想的事" : "也可以写下你的回答",choices:page.choices)
        next.action=first ? "show":"reply";board=next;observedAt=now;settledAt=nil
        canvas.setBoard(next)
    }
    func startExercise(_ selected:Bool?=nil){
        daily=true;canvas.daily=true
        exerciseMode=selected ?? (CommandLine.arguments.contains("--exercise") || CommandLine.arguments.contains("--demo"))
        if exerciseMode && !canvas.mode.itemTitles.contains("本地演示") {canvas.mode.addItem(withTitle:"本地演示")}
        if !exerciseMode && canvas.mode.itemTitles.contains("本地演示") {canvas.mode.removeItem(withTitle:"本地演示")}
        canvas.mode.selectItem(at:selected==nil && CommandLine.arguments.contains("--demo") ? 2:0)
        let welcome=ExercisePage(title:"你想|聊什么？",choices:[],art:.wave)
        showExercise(exerciseMode ? .opening : welcome,first:true)
    }
    func changeMode(_ live:Bool){
        guard daily,!closing else{return}
        idleRelease?.cancel();timeout?.cancel();request=nil;bridge.stop()
        if canvas.mode.indexOfSelectedItem==1 && credential.isEmpty && ProcessInfo.processInfo.environment["DEEPSEEK_API_KEY"]==nil {
            let alert=NSAlert();alert.messageText="连接 DeepSeek Flash";alert.informativeText="密钥仅在本次白板会话使用，发送到 api.deepseek.com。"
            let field=NSSecureTextField(frame:NSRect(x:0,y:0,width:310,height:28));field.placeholderString="API Key"
            alert.accessoryView=field;alert.addButton(withTitle:"连接");alert.addButton(withTitle:"取消");alert.window.initialFirstResponder=field
            if alert.runModal() == .alertFirstButtonReturn {credential=field.stringValue.trimmingCharacters(in:.whitespacesAndNewlines)}
            if credential.isEmpty {canvas.mode.selectItem(at:0)}
        }
        if canvas.submitted { generate() }
        else {warmModel();if receivedHeadline {canvas.feedback.stringValue="空格继续 · Enter 回答 · Esc 退出"}}
    }
    func warmModel(){
        guard daily,!closing,request==nil,canvas.mode.indexOfSelectedItem != 2 else{return}
        try? bridge.ask(["warm":true,"request":"warm","provider":canvas.mode.indexOfSelectedItem==1 ? "flash":"codex","exercise":exerciseMode])
        idleRelease?.cancel()
        let release=DispatchWorkItem { [weak self] in if self?.request==nil {self?.bridge.stop()} }
        idleRelease=release;DispatchQueue.main.asyncAfter(deadline:.now()+45,execute:release)
    }
    func generate(){
        guard daily,!closing else{return}
        idleRelease?.cancel();let id=UUID().uuidString;request=id;receivedHeadline=false
        canvas.retry.isHidden=true
        if canvas.mode.indexOfSelectedItem==2 {
            canvas.feedback.stringValue="正在翻页…"
            DispatchQueue.main.async { [weak self] in
                guard let self,self.request==id,!self.closing else{return}
                let page=self.lastAnswer.map{ExerciseDemo.next($0,previous:self.lastQuestion)} ?? ExerciseDemo.skipping(self.lastQuestion)
                self.metrics["localSceneAt"]=self.now;self.showExercise(page);CATransaction.flush()
                self.metrics["headlineCommittedAt"]=self.now;self.request=nil;self.report("visible")
            }
            return
        }
        canvas.feedback.stringValue="正在生成下一句…"
        do {
            var job:[String:Any]=["provider":canvas.mode.indexOfSelectedItem==1 ? "flash":"codex","exercise":exerciseMode,"credential":canvas.mode.indexOfSelectedItem==1 ? credential:"","request":id,"question":lastQuestion,"action":lastAnswer==nil ? "continue":"answer","history":Array(history.dropLast().suffix(4))]
            if let lastAnswer {job["answer"]=lastAnswer}
            try bridge.ask(job)
            let work=DispatchWorkItem { [weak self] in
                guard let self,self.request==id else{return};self.bridge.stop();self.failed()
            }
            timeout?.cancel();timeout=work;DispatchQueue.main.asyncAfter(deadline:.now()+65,execute:work)
        } catch { bridge.stop();failed() }
    }
    func failed(_ reason:String="unavailable"){
        guard daily,!closing,request != nil else{return}
        timeout?.cancel();request=nil
        canvas.group.isHidden=false;canvas.liveLead.isHidden=true
        if receivedHeadline {
            canvas.feedback.stringValue="选项暂未送达，仍可输入回复"
        }else{
            let reasons=["invalid-key":"DeepSeek 拒绝了密钥，请重新选择 DeepSeek 输入新密钥","balance":"DeepSeek 账户余额不足","rate-limit":"模型请求过于频繁，请稍后重试"]
            if reason=="invalid-key" {credential=""}
            canvas.feedback.stringValue=reasons[reason] ?? "模型暂未接通，可重试或切换模型"
            canvas.retry.isHidden=false
        }
        report("visible")
    }
    func modelEvent(_ message:[String:Any]){
        guard daily,!closing,let id=request,message["request"] as? String==id else{return}
        for key in ["modelStart","firstDelta"] {if let value=message[key] as? Double {metrics[key]=value}}
        switch message["kind"] as? String {
        case "lead":
            guard !receivedHeadline,canvas.submitted,let text=message["title"] as? String else{return}
            canvas.previewClause(text);CATransaction.flush();metrics["firstClauseCommittedAt"]=now
        case "headline":
            guard let title=message["title"] as? String,!receivedHeadline else{return}
            receivedHeadline=true;metrics["headlineEmittedAt"]=message["at"] as? Double;metrics["headlineReceivedAt"]=now
            let page=ExercisePage(title:title,choices:[],art:exercise.art)
            showExercise(page);CATransaction.flush();metrics["headlineCommittedAt"]=now
        case "done":
            guard receivedHeadline else{failed();return}
            timeout?.cancel()
            exercise.choices=message["choices"] as? [String] ?? []
            if let raw=message["art"] as? String,let art=ExerciseArt(rawValue:raw){exercise.art=art}
            exercise.curve=message["curve"] as? [[Double]]
            if let custom=message["canvas"],let data=try? JSONSerialization.data(withJSONObject:custom) {
                exercise.custom=try? JSONDecoder().decode(CanvasSpec.self,from:data)
            }
            board.interaction?.choices=exercise.choices;if !exerciseMode,exercise.custom==nil,let raw=message["figure"],let data=try? JSONSerialization.data(withJSONObject:raw),
               let figure=try? JSONDecoder().decode(CanvasSpec.self,from:data) {exercise.custom=exercise.withFigure(figure)}
            board.canvas=exerciseMode ? exercise.canvas : exercise.custom;board.action="patch";board.sceneSequence=1
            canvas.replaceChoices(exercise.choices);canvas.setBoard(board);canvas.layoutSubtreeIfNeeded()
            CATransaction.flush();metrics["modelDoneAt"]=message["at"] as? Double;metrics["detailsCommittedAt"]=now;request=nil
            let release=DispatchWorkItem { [weak self] in
                guard let self,self.request==nil else{return};self.bridge.stop()
            }
            idleRelease=release;DispatchQueue.main.asyncAfter(deadline:.now()+45,execute:release)
        case "error":failed(message["reason"] as? String ?? "unavailable");return
        default:return
        }
        report("visible")
    }
    let folder=ProcessInfo.processInfo.environment["DOT_WHITEBOARD_DATA"].map{URL(fileURLWithPath:$0)} ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/DotWhiteboard")
    var state:URL { folder.appendingPathComponent("content.json") }
    var status:URL { folder.appendingPathComponent("status.json") }
    func report(_ visibility:String) {
        let value:[String:Any] = ["editing":editing,"source":daily ? (canvas.mode.indexOfSelectedItem==2 ? "exercise-demo" : (canvas.mode.indexOfSelectedItem==1 ? "flash":"codex")) : "dot","metrics":metrics,"stableNodes":true,"sceneStream":true,"pid":ProcessInfo.processInfo.processIdentifier,"visibility":visibility,"title":board.title,"showID":board.showID,"updatedAt":Date().timeIntervalSince1970,"windowNumber":window?.windowNumber ?? 0,"turnID":board.turnID ?? "","writtenAt":board.writtenAt ?? 0,"rendererObservedAt":observedAt,"renderCommittedAt":committedAt,"settledAt":settledAt ?? 0]
        if let data=try? JSONSerialization.data(withJSONObject:value,options:.sortedKeys) { try? data.write(to:status,options:.atomic) }
    }
    func saveReply(_ text:String?)->Bool {
        guard !closing,let turn=board.turnID,board.interaction != nil else{return false}
        if daily {
            metrics=["submittedAt":now];lastQuestion=board.title;lastAnswer=text
            var entry=["页面":lastQuestion,"操作":text==nil ? "继续":"回答"];entry["回答"]=text
            history.append(entry);history=Array(history.suffix(5))
            return true
        }
        if let data=try? Data(contentsOf:state),let disk=try? JSONDecoder().decode(Board.self,from:data),
           disk.turnID != turn || disk.showID != board.showID {refresh();return false}
        var value:[String:Any]=["id":UUID().uuidString,"showID":board.showID,"turnID":turn,"kind":text==nil ? "continue":"answer","createdAt":Date().timeIntervalSince1970]
        value["text"]=text
        do {let data=try JSONSerialization.data(withJSONObject:value,options:.sortedKeys)
            try data.write(to:folder.appendingPathComponent("pending-reply.json"),options:.atomic);return true
        } catch {return false}
    }
    func quit() {
        guard !closing else{return};closing=true
        request=nil;timeout?.cancel();idleRelease?.cancel();bridge.stop();ticker?.invalidate();watcher?.cancel()
        stopFollowing();report("dismissed")
        if NSWorkspace.shared.accessibilityDisplayShouldReduceMotion { NSApp.terminate(nil); return }
        NSAnimationContext.runAnimationGroup({ context in context.duration=0.18; window.animator().alphaValue=0 }, completionHandler:{ NSApp.terminate(nil) })
    }
    func applicationDidFinishLaunching(_ notification:Notification) {
        try? FileManager.default.createDirectory(at:folder,withIntermediateDirectories:true)
        let screen=NSScreen.screens.first(where:{ NSMouseInRect(NSEvent.mouseLocation,$0.frame,false) }) ?? NSScreen.main!
        window=BoardWindow(contentRect:screen.frame,styleMask:[.borderless],backing:.buffered,defer:false)
        window.title="Dot 白板"; window.level = testWindow ? NSWindow.Level(rawValue:Int(CGWindowLevelForKey(.desktopWindow))+1) : .floating
        window.collectionBehavior=[.moveToActiveSpace,.fullScreenAuxiliary]
        canvas=Canvas(frame:screen.frame);canvas.onSettled={ [weak self] turn in guard let self=self,!self.closing,self.board.turnID==turn else{return};self.settledAt=Date().timeIntervalSince1970;self.report("visible") }; canvas.onReply={ [weak self] text in self?.saveReply(text) ?? false }; canvas.quit={ [weak self] in self?.quit() }; window.contentView=canvas
        (NSApp as? WhiteboardApplication)?.escape={ [weak self] in self?.quit() }
        escapeMonitor=NSEvent.addLocalMonitorForEvents(matching:.keyDown){ [weak self] event in
            if event.keyCode==53 {self?.quit();return nil}
            if event.modifierFlags.contains(.command) {
                if event.charactersIgnoringModifiers=="o" {self?.openDocument();return nil}
                if event.charactersIgnoringModifiers=="s",self?.board.pageID != nil {self?.saveDocument();return nil}
            }
            guard let self,event.window===self.window,
                  event.modifierFlags.intersection([.command,.control,.option,.shift]).isEmpty else{return event}
            let editor=self.window.firstResponder as? NSTextView
            if event.keyCode==49 {
                if self.spaceBelongsToEditor(){return event}
                if !event.isARepeat {self.advance()}
                return nil
            }
            if editor==nil,self.board.pageID != nil {
                if event.keyCode==123 {self.navigate(-1);return nil}
                if event.keyCode==124 {self.advance();return nil}
            }
            return event
        }
        if testWindow {
            for (sig,code,char) in [(SIGUSR1,UInt16(53),"\u{1b}"),(SIGUSR2,UInt16(49)," ")] {
                let source=DispatchSource.makeSignalSource(signal:sig,queue:.main)
                signal(sig,SIG_IGN)
                source.setEventHandler { [weak self] in
                    guard let self,let e=NSEvent.keyEvent(with:.keyDown,location:.zero,modifierFlags:[],
                          timestamp:ProcessInfo.processInfo.systemUptime,windowNumber:self.window.windowNumber,context:nil,
                          characters:char,charactersIgnoringModifiers:char,isARepeat:false,keyCode:code) else{return}
                    NSApp.postEvent(e,atStart:true)
                }
                testKeys.append(source);source.resume()
            }
        }
        canvas.modeChanged={ [weak self] live in self?.changeMode(live) }
        canvas.retryReply={ [weak self] in self?.generate() }
        canvas.didSubmit={ [weak self] in
            guard let self,self.daily else{return};self.metrics["feedbackCommittedAt"]=self.now
            self.generate();self.report("visible")
        }
        bridge.onEvent={ [weak self] message in self?.modelEvent(message) }
        bridge.onFailure={ [weak self] in self?.failed() }
        canvas.editStatus={ [weak self] active in guard let self,!self.closing else{return};self.editing=active;self.report("visible") }
        canvas.onBeginInput={ [weak self] in self?.warmModel() }
        canvas.chooseFile={ [weak self] in self?.openDocument() }
        canvas.advance={ [weak self] in self?.advance() }
        canvas.navigate={ [weak self] offset in self?.navigate(offset) }
        canvas.saveFile={ [weak self] in self?.saveDocument() }
        canvas.newConversation={ [weak self] fitness in
            guard let self else{return};self.request=nil;self.timeout?.cancel();self.idleRelease?.cancel();self.bridge.stop()
            self.stopFollowing();self.history=[];self.metrics=[:];self.pageIDs=[];self.ticker?.invalidate()
            self.startExercise(fitness);self.report("visible")
        }
        window.setFrame(screen.frame,display:true)
        let args=CommandLine.arguments
        let initial=try? Data(contentsOf:state)
        if let index=args.firstIndex(of:"--external"),args.indices.contains(index+1),
           let data=initial,let model=try? JSONDecoder().decode(Board.self,from:data),
           model.showID==args[index+1],model.action != "close" { refresh() }
        else if args.contains("--external"){NSApp.terminate(nil);return}
        else if !isPluginRenderer && (args.contains("--exercise") || args.contains("--demo") || args.contains("--standalone")) {
            bytes=initial;startExercise()
        } else {
            bytes=initial
            var home=Board()
            let prior=initial.flatMap{try? JSONDecoder().decode(Board.self,from:$0)}
            home.directThread=prior?.directThread ?? prior?.followThread
            home.showID=UUID().uuidString;home.pageID="home";home.pageCount=1;home.pageIndex=0
            home.title="在 Dot 里，接着聊。";home.subtitle="动态白板"
            home.body="在个人 dot 的主对话里说「用动态白板」。"
            board=home;canvas.setBoard(home)
            if !testWindow {DispatchQueue.main.async { [weak self] in
                guard let self,!self.closing,self.board.pageID=="home" else{return}
                self.canvas.returnToChat()
            }}
        }
        if testWindow {window.orderBack(nil)}else{window.makeKeyAndOrderFront(nil); window.makeFirstResponder(canvas); NSApp.activate(ignoringOtherApps:true)}
        CATransaction.flush();report("visible")
        watchFD=open(folder.path,O_EVTONLY)
        if watchFD >= 0 {
            let source=DispatchSource.makeFileSystemObjectSource(fileDescriptor:watchFD,eventMask:.write,queue:.main)
            source.setEventHandler { [weak self] in self?.refresh() }
            let fd=watchFD; source.setCancelHandler { Darwin.close(fd) }; watcher=source; source.resume();refresh()
        }
    }
    func documentCommand(_ name:String,_ args:[String:Any],file:URL?=nil){
        let proc=Process(),pipe=Pipe()
        proc.executableURL=URL(fileURLWithPath:"/usr/bin/python3")
        let script=Bundle.main.bundleURL.resolvingSymlinksInPath().deletingLastPathComponent().appendingPathComponent("scripts/演示文稿.py").path
        proc.arguments=["-B",script,name]+(file.map {["--file",$0.path]} ?? [])
        proc.standardInput=pipe;proc.standardOutput=FileHandle.nullDevice;proc.standardError=FileHandle.nullDevice
        proc.terminationHandler={ [weak self] task in DispatchQueue.main.async {
            if task.terminationStatus != 0 {self?.canvas.feedback.isHidden=false;self?.canvas.feedback.stringValue="文稿未更新，请检查文件或当前页"}
        }}
        do {try proc.run();if file==nil {try pipe.fileHandleForWriting.write(contentsOf:JSONSerialization.data(withJSONObject:args))}
            try pipe.fileHandleForWriting.close()
        }catch {canvas.feedback.isHidden=false;canvas.feedback.stringValue="无法读取文稿"}
    }
    func spaceBelongsToEditor()->Bool {
        guard let editor=window.firstResponder as? NSTextView else{return false}
        return editor.hasMarkedText() || !editor.string.isEmpty
    }
    func advance(){
        guard !closing,!(canvas.submitted && board.visualStyle?.hasPrefix("live-")==true) else{return}
        if let index=board.pageIndex,index+1<pageIDs.count {navigate(1);return}
        if board.interaction != nil {canvas.finishTurn(nil);return}
        canvas.feedback.stringValue="已到最后一页 · Esc 退出"
    }
    func navigate(_ offset:Int){
        guard !(canvas.submitted && board.visualStyle?.hasPrefix("live-")==true),!closing,let index=board.pageIndex,pageIDs.indices.contains(index+offset),let id=board.pageID else{return}
        documentCommand("navigate",["session":board.showID,"fromPage":id,"page":pageIDs[index+offset]])
    }
    func openDocument(){
        let picker=NSOpenPanel();picker.allowedContentTypes=[.json];picker.allowsMultipleSelection=false
        if picker.runModal() == .OK,let url=picker.url {documentCommand("present",[:],file:url)}
    }
    func saveDocument(){
        guard let data=try? Data(contentsOf:state),let dict=(try? JSONSerialization.jsonObject(with:data)) as? [String:Any],
              let doc=dict["document"] as? [String:Any],dict["showID"] as? String==board.showID else{return}
        let picker=NSSavePanel();picker.allowedContentTypes=[.json];picker.nameFieldStringValue=(doc["title"] as? String ?? "演示")+".白板.json"
        if picker.runModal() == .OK,let url=picker.url {
            do {try JSONSerialization.data(withJSONObject:doc,options:[.prettyPrinted,.sortedKeys]).write(to:url,options:.atomic)}
            catch {canvas.feedback.isHidden=false;canvas.feedback.stringValue="无法保存文稿"}
        }
    }
    func stopFollowing(){
        let previous=follower;follower=nil
        if let previous,previous.isRunning {previous.terminate()}
    }
    func startFollowing(_ page:Board){
        stopFollowing()
        guard let thread=page.followThread,let offset=page.followOffset else{return}
        let proc=Process()
        let script=Bundle.main.bundleURL.resolvingSymlinksInPath().deletingLastPathComponent().appendingPathComponent("scripts/当前聊天.py")
        proc.executableURL=URL(fileURLWithPath:"/usr/bin/python3")
        proc.arguments=["-B",script.path,page.showID,thread,String(offset)]
        proc.standardInput=FileHandle.nullDevice;proc.standardOutput=FileHandle.nullDevice;proc.standardError=FileHandle.nullDevice
        proc.terminationHandler={ [weak self] ended in DispatchQueue.main.async {
            guard let self,self.follower===ended,!self.closing else{return}
            self.follower=nil;self.canvas.feedback.stringValue="聊天连接已结束，可从当前聊天重新连接"
        }}
        do {try proc.run();follower=proc}
        catch {canvas.feedback.stringValue="未能连接当前聊天"}
    }
    func applicationShouldHandleReopen(_ sender:NSApplication,hasVisibleWindows flag:Bool)->Bool {
        guard !closing else{return false};refresh(); window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps:true); return true
    }
    func refresh() {
        guard !closing,let data=try? Data(contentsOf:state), data != bytes,
              let new=try? JSONDecoder().decode(Board.self,from:data) else { return }
        bytes=data;observedAt=now
        if new.action == "close" {if new.showID==board.showID {quit()};return}
        if daily {
            guard new.action=="show" else{return}
            request=nil;timeout?.cancel();bridge.stop();daily=false;canvas.daily=false;metrics=[:]
        }
        if new.action=="patch" && (canvas.submitted || new.showID != board.showID || new.turnID != board.turnID){return}
        if let all=(try? JSONSerialization.jsonObject(with:data)) as? [String:Any],
           let doc=all["document"] as? [String:Any],let pages=doc["pages"] as? [[String:Any]] {pageIDs=pages.compactMap{$0["id"] as? String}}else{pageIDs=[]}
        let samePage=new.showID==board.showID && new.pageID != nil && new.pageID==board.pageID
        if new.action=="caption" && samePage && new.turnID==board.turnID {
            board=new;canvas.board=new
            if new.interaction==nil {canvas.second.stringValue=new.title}
            canvas.tick()
            canvas.needsLayout=true;canvas.layoutSubtreeIfNeeded()
            CATransaction.flush();committedAt=now;report("visible");return
        }
        if new.action=="catalog" && samePage {
            board=new;canvas.board=new;canvas.navigationChrome()
            if canvas.submitted,let delivery=new.followDelivery {
                canvas.feedback.stringValue=delivery=="queued" ? "已排入当前聊天 · 等待处理" : "操作已保留 · 等待当前聊天读取"
            }
            CATransaction.flush();committedAt=now;report("visible");return
        }
        if new.action=="edit" && samePage && !canvas.submitted && new.canvas != nil && new.canvas != board.canvas && new.title==board.title && new.interaction==board.interaction && new.scene==board.scene && new.body==board.body && board.canvas != nil {
            var patch=new;patch.action="patch";board=new;canvas.setBoard(patch);canvas.navigationChrome();CATransaction.flush();committedAt=now;report("visible");return
        }
        if new.showID != board.showID {drafts.removeAll();startFollowing(new)}
        if new.action=="navigate",let id=board.pageID,!canvas.submitted {drafts[id]=canvas.input.stringValue}
        let show=new.showID != board.showID;observedAt=Date().timeIntervalSince1970;settledAt=nil; board=new; canvas.setBoard(new)
        if new.action=="navigate" {canvas.input.stringValue=drafts[new.pageID ?? ""] ?? ""}
        ticker?.invalidate(); ticker=nil
        if new.endsAt != nil { ticker=Timer.scheduledTimer(withTimeInterval:1,repeats:true) { [weak self] _ in self?.canvas.tick() }; ticker?.tolerance=0.1 }
        if show && !testWindow { window.makeKeyAndOrderFront(nil); if canvas.input.currentEditor()==nil {window.makeFirstResponder(canvas)}; NSApp.activate(ignoringOtherApps:true) }
        CATransaction.flush();committedAt=now;report("visible")
    }
}
@main
struct WhiteboardMain {
static func main() throws {
    signal(SIGPIPE,SIG_IGN)
if CommandLine.arguments.count==3 && CommandLine.arguments[1]=="--patch-test" {
    let app=NSApplication.shared;app.setActivationPolicy(.prohibited)
    let data=try Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[2]))
    var model=try JSONDecoder().decode(Board.self,from:data);model.turnID="fixture";model.showID="fixture";model.action="update"
    let view=Canvas(frame:NSRect(x:0,y:0,width:1440,height:900));view.setBoard(model)
    view.input.stringValue="正在输入，不可丢失";let count=view.choices.count
    model.action="patch";model.sceneSequence=1;model.canvas?.nodes[0].text="新表达。";view.setBoard(model)
    precondition(view.input.stringValue=="正在输入，不可丢失" && view.choices.count==count && !view.submitted)
    precondition(view.board.canvas?.nodes[0].text=="新表达。")
    view.submitted=true;model.canvas?.nodes[0].text="不应出现";view.setBoard(model)
    precondition(view.board.canvas?.nodes[0].text=="新表达。")
    print("PASS native same-turn patch preserves input/choices; submitted rejects patch");exit(0)
}
if CommandLine.arguments.count==3 && CommandLine.arguments[1]=="--timeline-test" {
    let app=NSApplication.shared;app.setActivationPolicy(.prohibited)
    let data=try Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[2]))
    let model=try JSONDecoder().decode(Board.self,from:data)
    let view=DiagramView(frame:NSRect(x:0,y:0,width:1200,height:600));view.spec=model.canvas;view.render()
    var count=0
    for (_,node) in view.animated {for track in node.timeline ?? [] {
        guard let a=view.timelineAnimation(track),a.values?.count==track.keys.count,a.keyTimes?.last==1,a.duration>0 else{fatalError("Invalid timeline")};count+=1
    }}
    view.animate();print("PASS native timeline tracks: \(count); finite duration; no window/state access");exit(count>0 ? 0 : 1)
}
if CommandLine.arguments.count==4 && CommandLine.arguments[1]=="--render-test" {
    let app=NSApplication.shared;app.setActivationPolicy(.prohibited)
    let data=try Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[2]))
    let model=try JSONDecoder().decode(Board.self,from:data)
    let view=Canvas(frame:NSRect(x:0,y:0,width:1440,height:900));view.setBoard(model);view.layoutSubtreeIfNeeded()
    let bitmap=view.bitmapImageRepForCachingDisplay(in:view.bounds)!;view.cacheDisplay(in:view.bounds,to:bitmap)
    try bitmap.representation(using:.png,properties:[:])!.write(to:URL(fileURLWithPath:CommandLine.arguments[3]));exit(0)
}
let app=WhiteboardApplication.shared
let delegate=Delegate()
app.setActivationPolicy(delegate.testWindow ? .prohibited : .regular)
app.delegate=delegate
app.run()

}
}
