import Foundation
import Vision

struct Reading: Codable {
    let text: String
    let left: Double
    let top: Double
    let width: Double
    let height: Double
    let confidence: Float
}

let tokenPattern = try NSRegularExpression(pattern: "\\S+")
let encoder = JSONEncoder()
let arguments = Array(CommandLine.arguments.dropFirst())
guard let language = arguments.first, arguments.count > 1 else {
    FileHandle.standardError.write(Data("Usage: vision_read language-list input.png ...\n".utf8))
    exit(1)
}

for filename in arguments.dropFirst() {
    let file = URL(fileURLWithPath: filename)
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = false
    request.recognitionLanguages = language.split(separator: "+").map(String.init)
    let handler = VNImageRequestHandler(url: file)
    try handler.perform([request])
    var readings = [Reading]()
    for observation in request.results ?? [] {
        guard let candidate = observation.topCandidates(1).first else { continue }
        let text = candidate.string
        for match in tokenPattern.matches(in: text, range: NSRange(text.startIndex..., in: text)) {
            guard let span = Range(match.range, in: text) else { continue }
            let box = (try candidate.boundingBox(for: span))?.boundingBox ?? observation.boundingBox
            readings.append(Reading(text: String(text[span]), left: box.minX,
                                    top: 1.0 - box.maxY, width: box.width,
                                    height: box.height, confidence: candidate.confidence))
        }
    }
    let payload = try encoder.encode(readings)
    let output = file.deletingPathExtension().appendingPathExtension("json")
    try payload.write(to: output, options: .atomic)
}
