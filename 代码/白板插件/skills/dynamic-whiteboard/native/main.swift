// 动态白板 · 原生窗口
// 一个无边框全屏窗口，里面是渲染引擎（engine/）。白板的数据和交互由 scripts/board_server.py 负责，
// 这里只做三件事：起服务、开窗口、在页面要求或服务结束时退出。
import Cocoa
import WebKit

final class BoardWindow: NSWindow {
    override var canBecomeKey: Bool { return true }
    override var canBecomeMain: Bool { return true }
}

final class BoardApp: NSObject, NSApplicationDelegate, WKScriptMessageHandler, WKNavigationDelegate {
    var window: BoardWindow!
    var web: WKWebView!
    var server: Process?
    var quitting = false
    var fullScreen = true

    func applicationDidFinishLaunching(_ notification: Notification) {
        let args = CommandLine.arguments
        var show = ""
        if let i = args.firstIndex(of: "--show"), i + 1 < args.count { show = args[i + 1] }
        fullScreen = !args.contains("--test-window")
        buildMenu()

        let screen = NSScreen.main ?? NSScreen.screens[0]
        let frame = fullScreen ? screen.frame : NSRect(x: 160, y: 120, width: 1280, height: 800)
        let style: NSWindow.StyleMask = fullScreen ? [.borderless] : [.titled, .closable, .resizable, .miniaturizable]
        window = BoardWindow(contentRect: frame, styleMask: style, backing: .buffered, defer: false)
        window.title = "动态白板"
        window.isReleasedWhenClosed = false
        window.backgroundColor = NSColor(srgbRed: 0xFB / 255.0, green: 0xF5 / 255.0, blue: 0xEF / 255.0, alpha: 1)
        window.collectionBehavior = [.moveToActiveSpace, .fullScreenAuxiliary]
        window.alphaValue = 0

        let config = WKWebViewConfiguration()
        config.userContentController.add(self, name: "board")
        web = WKWebView(frame: window.contentView!.bounds, configuration: config)
        web.autoresizingMask = [.width, .height]
        web.navigationDelegate = self
        web.isHidden = true
        window.contentView!.addSubview(web)

        NSApp.setActivationPolicy(.regular)
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        _ = window.makeFirstResponder(web)
        startServer(show: show)
    }

    func pythonPath() -> String {
        for candidate in ["/usr/bin/python3", "/opt/homebrew/bin/python3", "/usr/local/bin/python3"] {
            if FileManager.default.isExecutableFile(atPath: candidate) { return candidate }
        }
        return "/usr/bin/python3"
    }

    func startServer(show: String) {
        let root = Bundle.main.bundleURL.deletingLastPathComponent()
        let script = root.appendingPathComponent("scripts").appendingPathComponent("board_server.py").path
        let process = Process()
        process.executableURL = URL(fileURLWithPath: pythonPath())
        process.arguments = ["-B", script, "--show", show, "--host", "wk"]
        process.environment = ProcessInfo.processInfo.environment
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = FileHandle.nullDevice
        process.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async { self?.quit() }
        }
        do {
            try process.run()
        } catch {
            fail("无法启动 python3：\(error.localizedDescription)")
            return
        }
        server = process
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let handle = pipe.fileHandleForReading
            var buffer = Data()
            while true {
                let chunk = handle.availableData
                if chunk.isEmpty { break }
                buffer.append(chunk)
                guard let text = String(data: buffer, encoding: .utf8), let newline = text.firstIndex(of: "\n") else { continue }
                let line = String(text[..<newline]).trimmingCharacters(in: .whitespaces)
                let fields = line.split(separator: " ")
                if fields.count == 3, fields[0] == "PORT", let port = Int(fields[1]), let url = URL(string: "http://127.0.0.1:\(port)/\(fields[2])/") {
                    DispatchQueue.main.async { self?.web.load(URLRequest(url: url)) }
                }
                break
            }
        }
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        web.isHidden = false
        NSAnimationContext.runAnimationGroup({ context in
            context.duration = 0.22
            self.window.animator().alphaValue = 1
        }, completionHandler: nil)
        _ = self.window.makeFirstResponder(self.web)
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        fail("白板页面加载失败：\(error.localizedDescription)")
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        if let body = message.body as? String, body == "quit" { quit() }
    }

    func applicationDidBecomeActive(_ notification: Notification) {
        if fullScreen { NSApp.presentationOptions = [.hideDock, .hideMenuBar] }
    }

    func applicationDidResignActive(_ notification: Notification) {
        NSApp.presentationOptions = []
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { return true }

    func applicationWillTerminate(_ notification: Notification) {
        if let process = server, process.isRunning { process.terminate() }
    }

    func quit() {
        if quitting { return }
        quitting = true
        if let process = server, process.isRunning { process.terminate() }
        NSApp.terminate(nil)
    }

    func fail(_ text: String) {
        let alert = NSAlert()
        alert.messageText = "动态白板"
        alert.informativeText = text
        alert.runModal()
        quit()
    }

    func buildMenu() {
        let main = NSMenu()
        let appItem = NSMenuItem()
        main.addItem(appItem)
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "退出动态白板", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu
        let editItem = NSMenuItem()
        main.addItem(editItem)
        let edit = NSMenu(title: "编辑")
        edit.addItem(withTitle: "撤销", action: Selector(("undo:")), keyEquivalent: "z")
        edit.addItem(withTitle: "剪切", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        edit.addItem(withTitle: "拷贝", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: "粘贴", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        edit.addItem(withTitle: "全选", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        editItem.submenu = edit
        NSApp.mainMenu = main
    }
}

let app = NSApplication.shared
let delegate = BoardApp()
app.delegate = delegate
app.run()
