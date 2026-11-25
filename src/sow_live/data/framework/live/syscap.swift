// syscap: capture macOS system audio (everything you hear, e.g. the customer
// on Teams/Zoom/Meet) via ScreenCaptureKit and write raw PCM to stdout.
//
// Output: mono, 32-bit float little-endian, 48 kHz, no header.
// Status lines go to stderr ("READY", "ERROR: ...").
//
// Needs macOS 13+ and Screen Recording permission for the terminal app that
// launches it (System Settings > Privacy & Security > Screen & System Audio Recording).
//
// Build: swiftc -O -o build/bin/syscap live/syscap/syscap.swift

import AVFoundation
import CoreMedia
import Foundation
import ScreenCaptureKit

setvbuf(stderr, nil, _IONBF, 0)

final class SystemAudioCapture: NSObject, SCStreamOutput, SCStreamDelegate {
    private var stream: SCStream?
    private let stdout = FileHandle.standardOutput
    private let audioQueue = DispatchQueue(label: "syscap.audio")
    private let screenQueue = DispatchQueue(label: "syscap.screen")
    private var loggedFormat = false

    func start() async throws {
        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
        guard let display = content.displays.first else {
            throw NSError(domain: "syscap", code: 1, userInfo: [NSLocalizedDescriptionKey: "no display found"])
        }
        let filter = SCContentFilter(display: display, excludingApplications: [], exceptingWindows: [])

        let config = SCStreamConfiguration()
        config.capturesAudio = true
        config.excludesCurrentProcessAudio = true
        config.sampleRate = 48_000
        config.channelCount = 1
        // Video is mandatory for an SCStream; keep it as cheap as possible.
        config.width = 2
        config.height = 2
        config.minimumFrameInterval = CMTime(value: 1, timescale: 1)
        config.queueDepth = 3

        let stream = SCStream(filter: filter, configuration: config, delegate: self)
        try stream.addStreamOutput(self, type: .audio, sampleHandlerQueue: audioQueue)
        try stream.addStreamOutput(self, type: .screen, sampleHandlerQueue: screenQueue)
        try await stream.startCapture()
        self.stream = stream
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .audio, sampleBuffer.isValid else { return }

        if !loggedFormat, let desc = CMSampleBufferGetFormatDescription(sampleBuffer),
           let asbd = CMAudioFormatDescriptionGetStreamBasicDescription(desc)?.pointee {
            loggedFormat = true
            FileHandle.standardError.write(
                "FORMAT rate=\(Int(asbd.mSampleRate)) channels=\(asbd.mChannelsPerFrame) bits=\(asbd.mBitsPerChannel) flags=\(asbd.mFormatFlags)\n"
                    .data(using: .utf8)!)
        }

        var bufferList = AudioBufferList()
        var blockBuffer: CMBlockBuffer?
        let status = CMSampleBufferGetAudioBufferListWithRetainedBlockBuffer(
            sampleBuffer,
            bufferListSizeNeededOut: nil,
            bufferListOut: &bufferList,
            bufferListSize: MemoryLayout<AudioBufferList>.size,
            blockBufferAllocator: nil,
            blockBufferMemoryAllocator: nil,
            flags: 0,
            blockBufferOut: &blockBuffer)
        guard status == noErr else { return }

        // channelCount = 1, so there is exactly one (non-interleaved) Float32 buffer.
        let buffer = bufferList.mBuffers
        if let data = buffer.mData, buffer.mDataByteSize > 0 {
            stdout.write(Data(bytes: data, count: Int(buffer.mDataByteSize)))
        }
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        FileHandle.standardError.write("ERROR: stream stopped: \(error.localizedDescription)\n".data(using: .utf8)!)
        exit(1)
    }
}

// Exit quietly when the reader goes away.
signal(SIGPIPE) { _ in exit(0) }
signal(SIGTERM) { _ in exit(0) }
signal(SIGINT) { _ in exit(0) }

let capture = SystemAudioCapture()
Task {
    do {
        try await capture.start()
        FileHandle.standardError.write("READY\n".data(using: .utf8)!)
    } catch {
        FileHandle.standardError.write("ERROR: \(error.localizedDescription)\n".data(using: .utf8)!)
        exit(2)
    }
}
dispatchMain()
