import Foundation

/// Receives the OnFlight Hub's 67-byte INS frames broadcast on UDP port 2000.
///
/// Plain BSD socket bound to all interfaces: unicast and broadcast both arrive, so the same code
/// works against the real Hub and against a local test sender in the simulator. On a physical
/// iPhone, receiving broadcast requires the `com.apple.developer.networking.multicast` entitlement.
final class HubListener {
    static let port: UInt16 = 2000
    static let frameSize = 67

    private let queue = DispatchQueue(label: "org.livefreeandfly.acroreplay.udp", qos: .userInteractive)
    private var running = false

    func start(onFrame: @escaping (Data, TimeInterval) -> Void) {
        guard !running else { return }
        running = true
        queue.async { self.receiveLoop(onFrame: onFrame) }
    }

    private func receiveLoop(onFrame: @escaping (Data, TimeInterval) -> Void) {
        let fd = socket(AF_INET, SOCK_DGRAM, 0)
        guard fd >= 0 else { NSLog("HubListener: socket() failed errno=\(errno)"); return }
        defer { close(fd) }
        var yes: Int32 = 1
        setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &yes, socklen_t(MemoryLayout<Int32>.size))
        setsockopt(fd, SOL_SOCKET, SO_BROADCAST, &yes, socklen_t(MemoryLayout<Int32>.size))
        var addr = sockaddr_in()
        addr.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_port = Self.port.bigEndian
        addr.sin_addr.s_addr = INADDR_ANY
        let bound = withUnsafePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size)) }
        }
        guard bound == 0 else { NSLog("HubListener: bind(\(Self.port)) failed errno=\(errno)"); return }
        var buffer = [UInt8](repeating: 0, count: 2048)
        while running {
            let n = recv(fd, &buffer, buffer.count, 0)
            if n == Self.frameSize {
                onFrame(Data(buffer[0..<Self.frameSize]), Date().timeIntervalSince1970)
            } else if n < 0 {
                NSLog("HubListener: recv failed errno=\(errno)")
                return
            }
        }
    }
}
