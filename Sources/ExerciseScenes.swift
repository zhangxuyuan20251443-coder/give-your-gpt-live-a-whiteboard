import AppKit

enum ExerciseArt: String { case track, wave, steps }

struct ExercisePage {
    var title: String
    var choices: [String]
    var art: ExerciseArt
    var curve: [[Double]]? = nil
    var custom: CanvasSpec? = nil
    static let opening = ExercisePage(title:"今天|运动了吗？",choices:["运动了","还没有","想休息"],art:.track)

    func withFigure(_ figure:CanvasSpec)->CanvasSpec {
        // 图形坐标独立于文字，可复用任意图形构图。
        let parts=title.split(separator:"|",maxSplits:1).map(String.init)
        var nodes=parts.enumerated().map { i,text in
            CanvasNode(type:"text",id:"wb-title-\(i)",text:text,x:i==0 ? 0:0.026,y:parts.count==1 ? 0.22:0.06+0.41*Double(i),
                       w:0.48,h:0.43,size:0.39,weight:i==0 ? "light":"semibold",color:i==0 ? "ink":"orange",motion:"rise")
        }
        for var n in figure.nodes {
            if let id=n.id {n.id="fig-"+id}
            n.x=0.53+0.47*(n.x ?? 0);n.w=(n.w ?? 0.5)*0.47
            if let pts=n.points {n.points=pts.map{[0.53+0.47*$0[0],$0[1]]}}
            nodes.append(n)
        }
        return CanvasSpec(nodes:Array(nodes.prefix(12)),transition:figure.transition)
    }
    var canvas: CanvasSpec {
        if let custom { return custom }
        let parts = title.split(separator:"|",maxSplits:1).map(String.init)
        var nodes: [CanvasNode] = []
        let coral="#F7513C", pink="#FA70AB", orange="#FF8066"
        func path(_ id:String,_ points:[[Double]],_ color:String,_ width:Double,_ delay:Double) {
            var n=CanvasNode(type:"bezier",id:id,points:points,stroke:width)
            n.color=color
            n.timeline=[TimelineTrack(property:"draw",keys:[[0,0],[0.06+delay,0],[0.88+delay,1]],easing:"ease-out")]
            nodes.append(n)
        }
        switch art {
        case .track:
            for i in 0..<5 {
                let rx=0.17-Double(i)*0.014,ry=0.40-Double(i)*0.032
                let cx=0.685,cy=0.46,k=0.552285
                func point(_ x:Double,_ y:Double)->[Double] { [x+0.17*(0.90-y),y] }
                let lane=[point(cx-rx,0.95),point(cx-rx,0.80),point(cx-rx,0.60),point(cx-rx,cy),
                          point(cx-rx,cy-k*ry),point(cx-k*rx,cy-ry),point(cx,cy-ry),
                          point(cx+k*rx,cy-ry),point(cx+rx,cy-k*ry),point(cx+rx,cy),
                          point(cx+rx,0.60),point(cx+rx,0.75),point(cx+rx,0.88)]
                path("lane-\(i)",lane,[coral,orange,pink,orange,coral][i],i==0 || i==4 ? 5:2.4,Double(i)*0.04)
                if i==2 {nodes[nodes.count-1].marker=PathMarker(radius:7,color:"ink",duration:1.12)}
            }
        case .wave:
            for i in 0..<5 {
                let d=Double(i)*0.038
                path("wave-\(i)",[[0.52,0.60+d],[0.65,0.62+d],[0.65,0.14+d],[0.76,0.17+d],
                     [0.85,0.19+d],[0.83,0.79+d],[0.995,0.58+d]],i==2 ? coral : (i%2==0 ? pink : orange),i==2 ? 7:2.8,Double(i)*0.045)
            }
        case .steps:
            for i in 0..<4 {
                let x=0.58+Double(i)*0.098, y=0.63-Double(i)*0.146
                path("step-\(i)",[[x,0.94],[x+0.045,0.83],[x+0.053,y+0.12],[x+0.094,y]],
                     [pink,orange,coral,coral][i],i==3 ? 10:5,Double(i)*0.075)
            }
        }
        if let curve {
            let mapped=curve.map { [0.54+$0[0]*0.45,0.05+$0[1]*0.88] }
            path("gesture",mapped,"ink",3,0.10)
        }
        func headline(_ id:String,_ value:String,_ x:Double,_ y:Double,_ w:Double,_ h:Double,_ weight:String,_ color:String,_ delay:Double) {
            var n=CanvasNode(type:"text",id:id,text:value,x:x,y:y,w:w,h:h,size:h*0.97,weight:weight,color:color)
            n.timeline=[TimelineTrack(property:"x",keys:[[0,id=="lead" ? -0.048:0.044],[0.48+delay,0]],easing:"ease-out"),
                        TimelineTrack(property:"opacity",keys:[[0,0],[0.035+delay,0],[0.32+delay,1]],easing:"ease-out")]
            nodes.append(n)
        }
        if parts.count==2 {
            let offset=art == .steps ? 0.02 : 0.062
            headline("lead",parts[0],0,art == .wave ? 0.14 : 0.055,0.52,0.44,"light","ink",0)
            headline("voice",parts[1],offset,art == .wave ? 0.53 : 0.46,0.535-offset,0.48,"semibold",coral,0.065)
        } else {
            headline("voice",parts.first ?? title,0.008,0.25,0.53,0.55,"semibold","ink",0)
        }
        return CanvasSpec(nodes:nodes,transition:art == .steps ? "push" : (art == .wave ? "crossfade":"lift"))
    }
}

// 离线演示的有限分支，供用户随时切换或在无联网时体验。
enum ExerciseDemo {
    static func skipping(_ current:String)->ExercisePage {
        if current.contains("舒服的节奏") {return ExercisePage(title:"今天先|聊到这儿。",choices:["重新开始"],art:.wave)}
        if current.contains("聊到这儿") {return .opening}
        return ExercisePage(title:"按自己|舒服的节奏来。",choices:["想休息","出门走走"],art:.wave)
    }
    static func next(_ answer:String, previous:String) -> ExercisePage {
        func page(_ title:String,_ choices:[String],_ art:ExerciseArt)->ExercisePage {
            ExercisePage(title:title,choices:choices,art:art)
        }
        if answer=="重新开始" {return .opening}
        if answer.contains("休息") || answer.contains("累") || answer.contains("不舒服") {
            return page("那就|歇一会儿。",["聊点别的","重新开始"],.wave)
        }
        if ["还没","没有","没动","没跑","没走","没练","没运动"].contains(where:answer.contains) {
            return page("想从|哪一步开始？",["出门走走","伸个懒腰","想休息"],.steps)
        }
        if ["运动了","刚跑","跑了","散步","走了","骑了","游了"].contains(where:answer.contains) {
            return page("动过之后，|感觉怎么样？",["很轻松","有点累"],.wave)
        }
        if answer=="出门走走" {return page("想往|哪个方向走？",["去公园","绕楼一圈"],.track)}
        if answer=="伸个懒腰" {return page("伸开手臂，|舒服些了吗？",["轻松多了","想休息"],.wave)}
        if answer.contains("轻松") || answer=="去公园" || answer=="绕楼一圈" {
            return page("留住这份|好心情。",["重新开始"],.wave)
        }
        if previous.contains("多说") {return page("我们可以|慢慢来。",["想休息","重新开始"],.wave)}
        return page("愿意|多说一点吗？",["想休息","重新开始"],.track)
    }
}

// 长连接只在第一次选择实时回复时建立。每条事件在主线程重新校验请求标识。
final class WhiteboardModelBridge {
    private var process: Process?
    private var writer: FileHandle?
    private var reader: FileHandle?
    private var serial=0
    private let readQueue=DispatchQueue(label:"local.dot.whiteboard.model")
    var onEvent: (([String:Any])->Void)?
    var onFailure: (()->Void)?

    func ask(_ job:[String:Any]) throws {
        if process == nil {
            let app=Bundle.main.bundleURL.resolvingSymlinksInPath()
            let script=app.deletingLastPathComponent().appendingPathComponent("scripts/模型对话.py")
            let proc=Process(), input=Pipe(), output=Pipe()
            proc.executableURL=URL(fileURLWithPath:"/usr/bin/python3")
            proc.arguments=["-B",script.path]
            proc.environment=ProcessInfo.processInfo.environment.merging(["PATH":"/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"]){ _,v in v }
            proc.standardInput=input;proc.standardOutput=output;proc.standardError=FileHandle.nullDevice
            try proc.run()
            process=proc;writer=input.fileHandleForWriting;reader=output.fileHandleForReading
            let generation=serial, handle=output.fileHandleForReading
            readQueue.async { [weak self] in
                var buffer=Data()
                while true {
                    let chunk=handle.availableData
                    if chunk.isEmpty {break}
                    buffer.append(chunk)
                    while let end=buffer.firstIndex(of:10) {
                        let line=Data(buffer[..<end]);buffer.removeSubrange(...end)
                        guard let obj=(try? JSONSerialization.jsonObject(with:line)) as? [String:Any] else{continue}
                        DispatchQueue.main.async { [weak self] in
                            guard let self,self.serial==generation else{return};self.onEvent?(obj)
                        }
                    }
                }
                DispatchQueue.main.async { [weak self] in
                    guard let self,self.serial==generation else{return};self.stop();self.onFailure?()
                }
            }
        }
        var data=try JSONSerialization.data(withJSONObject:job);data.append(10)
        try writer?.write(contentsOf:data)
    }

    func stop() {
        serial+=1
        try? writer?.close()
        writer=nil;reader=nil
        if let process,process.isRunning {process.terminate()}
        process=nil
    }
}
