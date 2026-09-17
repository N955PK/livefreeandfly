import Foundation

/// Records a flight only while the pilot has a routine active: the wing rock (or the on-screen Record button)
/// brackets a run, and just that stretch is written to Documents/Flights/<title> <date> <time>.bin in the
/// capture-kit record format (`<dH` little-endian unix seconds + payload length, then the payload) — the same
/// bytes the Python bridge writes, so the decoders and the web app's replay read phone files unchanged. There is
/// no always-on capture: ground time and between-routine flying never hit disk.
final class FlightRecorder {
    static let directory: URL = {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        return docs.appendingPathComponent("Flights", isDirectory: true)
    }()

    private let queue = DispatchQueue(label: "org.livefreeandfly.wingrock.recorder", qos: .utility)
    private var handle: FileHandle?      // open only while a run is recording
    private var url: URL?
    private var buffer = Data()
    private var boxJSON: String?         // latest aerobatic box; written as the first record of each file
    private var modelJSON: String?       // latest aircraft model, e.g. {"model":"eagle"}

    init() {
        try? FileManager.default.createDirectory(at: Self.directory, withIntermediateDirectories: true)
    }

    /// The aerobatic box the pilot has set; embedded at the head of each recording so a reopened flight
    /// comes back with its box.
    func setBox(_ json: String) { queue.async { self.boxJSON = json.isEmpty ? nil : json } }
    func setModel(_ key: String) { queue.async { self.modelJSON = key.isEmpty ? nil : "{\"model\":\"\(key)\"}" } }

    /// The wing rock (or the Record button) brackets a run: `startSequence` opens a file titled by the armed
    /// sequence/figure that captures just the bracketed stretch, `endSequence` closes it.
    func startSequence(title: String) {
        queue.async {
            self.close()
            let name = Self.sequenceFileName(title)
            let u = Self.directory.appendingPathComponent(name)
            FileManager.default.createFile(atPath: u.path, contents: nil)
            self.handle = try? FileHandle(forWritingTo: u)
            self.url = u
            self.buffer.removeAll(keepingCapacity: true)
            if let r = self.metaRecord(0xB0, self.boxJSON) { self.handle?.write(r) }
            if let r = self.metaRecord(0xB1, self.modelJSON) { self.handle?.write(r) }
            NSLog("FlightRecorder: recording -> %@", name)
        }
    }
    func endSequence() { queue.async { self.close() } }

    /// A recording is titled by the armed sequence/figure, then the date and time, so the pilot can tell their
    /// saved routines apart at a glance — e.g. "Primary Known 2026-09-17 12-07-30.bin".
    private static func sequenceFileName(_ title: String) -> String {
        let clean = title.map { "/:\\".contains($0) ? "-" : String($0) }.joined().trimmingCharacters(in: .whitespaces)
        let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd HH-mm-ss"
        return "\(clean.isEmpty ? "Sequence" : clean) \(f.string(from: Date())).bin"
    }

    /// Called for every received Hub frame; appended only while a run is being recorded.
    func record(_ payload: Data, wall: TimeInterval) {
        queue.async {
            guard self.handle != nil else { return }
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

    private func metaRecord(_ marker: UInt8, _ jsonString: String?) -> Data? {
        guard let jsonString, let json = jsonString.data(using: .utf8) else { return nil }
        var rec = Data(count: 10)
        let n = 1 + json.count
        rec.withUnsafeMutableBytes { raw in
            raw.storeBytes(of: Double(0).bitPattern.littleEndian, toByteOffset: 0, as: UInt64.self)
            raw.storeBytes(of: UInt16(n).littleEndian, toByteOffset: 8, as: UInt16.self)
        }
        rec.append(marker)
        rec.append(json)
        return rec
    }

    private func flush() {
        guard let handle, !buffer.isEmpty else { return }
        handle.write(buffer)
        buffer.removeAll(keepingCapacity: true)
    }

    private func close() {
        guard handle != nil else { return }
        flush()
        try? handle?.close()
        handle = nil
        url = nil
    }

    func finish() { queue.sync { close() } }
}
