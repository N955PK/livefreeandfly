import Foundation

/// Saves every received Hub frame to Documents/Flights/<date>_<time>.bin in the capture-kit record format
/// (`<dH` little-endian unix seconds + payload length, then the 67-byte payload) — the same bytes the Python
/// bridge writes to sessions/, so the decoders and the web app's replay read phone files unchanged.
/// A new file starts at each launch and whenever the INS re-initialises; files that never saw an initialised
/// INS are deleted on close so ground time doesn't pile up. ~14 MB per flying hour.
final class FlightRecorder {
    static let directory: URL = {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        return docs.appendingPathComponent("Flights", isDirectory: true)
    }()

    private let queue = DispatchQueue(label: "org.livefreeandfly.wingrock.recorder", qos: .utility)
    private var handle: FileHandle?
    private var url: URL?
    private var sawInit = false
    private var lastInit = false
    private var buffer = Data()
    private var boxJSON: String?      // latest aerobatic box; written as the first record of each flight file

    init() {
        try? FileManager.default.createDirectory(at: Self.directory, withIntermediateDirectories: true)
    }

    /// The aerobatic box the pilot has set; embedded at the head of each new flight file so a reopened flight
    /// comes back with its box.
    func setBox(_ json: String) { queue.async { self.boxJSON = json.isEmpty ? nil : json } }

    func record(_ payload: Data, wall: TimeInterval) {
        let initialised = payload.count == HubListener.frameSize && (payload[1] & 0x08) != 0
        queue.async {
            if initialised && !self.lastInit && self.sawInit { self.close() }   // INS came back: new flight file
            self.lastInit = initialised
            if initialised { self.sawInit = true }
            if self.handle == nil { self.open(at: wall) }
            var header = Data(count: 10)
            header.withUnsafeMutableBytes { raw in
                raw.storeBytes(of: wall.bitPattern.littleEndian, toByteOffset: 0, as: UInt64.self)
                raw.storeBytes(of: UInt16(payload.count).littleEndian, toByteOffset: 8, as: UInt16.self)
            }
            self.buffer.append(header)
            self.buffer.append(payload)
            if self.buffer.count >= 16 * 1024 { self.flush() }
        }
    }

    /// Recorded flights, newest first, as [{name, bytes}] for the web app's Flights list.
    static func list() -> [[String: Any]] {
        let files = (try? FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: [.fileSizeKey])) ?? []
        return files.filter { $0.pathExtension == "bin" }.sorted { $0.lastPathComponent > $1.lastPathComponent }.map {
            ["name": $0.lastPathComponent, "bytes": (try? $0.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0]
        }
    }

    private func open(at wall: TimeInterval) {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyyMMdd_HHmmss"
        let name = formatter.string(from: Date(timeIntervalSince1970: wall)) + ".bin"
        let url = Self.directory.appendingPathComponent(name)
        FileManager.default.createFile(atPath: url.path, contents: nil)
        handle = try? FileHandle(forWritingTo: url)
        self.url = url
        sawInit = false
        if let boxJSON, let json = boxJSON.data(using: .utf8) {   // box record: <dH header, 0xB0 marker, JSON
            var rec = Data(count: 10)
            let n = 1 + json.count
            rec.withUnsafeMutableBytes { raw in
                raw.storeBytes(of: Double(0).bitPattern.littleEndian, toByteOffset: 0, as: UInt64.self)
                raw.storeBytes(of: UInt16(n).littleEndian, toByteOffset: 8, as: UInt16.self)
            }
            rec.append(0xB0)
            rec.append(json)
            handle?.write(rec)
        }
        NSLog("FlightRecorder: recording to %@", name)
    }

    private func flush() {
        guard let handle, !buffer.isEmpty else { return }
        handle.write(buffer)
        buffer.removeAll(keepingCapacity: true)
    }

    private func close() {
        flush()
        try? handle?.close()
        if let url, !sawInit { try? FileManager.default.removeItem(at: url) }
        handle = nil
        url = nil
    }

    func finish() { queue.sync { close() } }
}
