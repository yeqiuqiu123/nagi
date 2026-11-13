import Foundation
import CryptoKit
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif

// Never expose the install secret to JavaScript, process arguments or logs.
// Mirrors owner_auth.py: every native request carries a fresh mutual proof.
public enum OwnerSession {
    public enum Failure: Error, Equatable { case unavailable, status(Int) }

    public static func secret(directory: String) throws -> String {
        let fd = open(directory + "/nagi-owner.json", O_RDONLY | O_NOFOLLOW | O_NONBLOCK)
        guard fd >= 0 else { throw Failure.unavailable }
        let handle = FileHandle(fileDescriptor: fd, closeOnDealloc: true)
        var info = stat()
        guard fstat(fd, &info) == 0, (info.st_mode & mode_t(S_IFMT)) == mode_t(S_IFREG),
              info.st_uid == getuid(), info.st_mode & 0o777 == 0o600, info.st_size <= 65536 else {
            throw Failure.unavailable
        }
        let data = handle.readDataToEndOfFile()
        guard let value = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              Set(value.keys) == ["version", "secret"], value["version"] as? Int == 1,
              let secret = value["secret"] as? String,
              secret.range(of: "\\A[A-Za-z0-9_-]{43}\\z", options: .regularExpression) != nil else {
            throw Failure.unavailable
        }
        return secret
    }

    public static func mac(_ secret: String, _ domain: String, _ origin: String, _ instance: String,
                           _ client: String, _ nonce: String, _ method: String, _ path: String, _ hash: String) -> Data {
        let message = [domain, origin, instance, client, nonce, method, path, hash].joined(separator: "\n")
        return Data(HMAC<SHA256>.authenticationCode(for: Data(message.utf8), using: SymmetricKey(data: Data(secret.utf8))))
    }

    public static func hex(_ value: Data) -> String { value.map { String(format: "%02x", $0) }.joined() }

    public static func decodeHex(_ value: String) -> Data? {
        guard value.range(of: "\\A[0-9a-f]{64}\\z", options: .regularExpression) != nil else { return nil }
        let chars = Array(value)
        return Data(stride(from: 0, to: chars.count, by: 2).map { UInt8(String(chars[$0...$0+1]), radix: 16)! })
    }

    public static func nonce() -> String {
        var generator = SystemRandomNumberGenerator()
        let bytes = (0..<32).map { _ in UInt8.random(in: .min ... .max, using: &generator) }
        return Data(bytes).base64EncodedString().replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "")
    }

    /// Exact loopback reader origin, e.g. http://127.0.0.1:47831.
    public static func validOrigin(_ origin: String) -> Bool {
        guard origin.range(of: "\\Ahttp://127\\.0\\.0\\.1:[1-9][0-9]{3,4}\\z", options: .regularExpression) != nil,
              let port = Int(origin.dropFirst("http://127.0.0.1:".count)) else { return false }
        return (1024...65535).contains(port)
    }

    private static func makeSession() -> URLSession {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.connectionProxyDictionary = [:]
        configuration.httpCookieStorage = nil
        configuration.urlCache = nil
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        return URLSession(configuration: configuration, delegate: NoRedirect(), delegateQueue: nil)
    }

    /// Verify the reader's server proof, then return the one-use client proof header.
    private static func authorize(_ session: URLSession, secret: String, origin: String,
                                  method: String, path: String, body: Data) async throws -> String {
        let bodyHash = hex(Data(SHA256.hash(data: body)))
        let client = nonce()
        var request = URLRequest(url: URL(string: origin + "/auth/challenge")!)
        request.httpMethod = "POST"
        request.httpBody = try JSONSerialization.data(withJSONObject:
            ["nonce": client, "method": method, "path": path, "bodyHash": bodyHash])
        request.timeoutInterval = 5
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("1", forHTTPHeaderField: "X-Progress-Desk")
        let (data, response) = try await session.data(for: request)
        guard (response as? HTTPURLResponse)?.statusCode == 200, data.count <= 4096,
              let challenge = try JSONSerialization.jsonObject(with: data) as? [String: String],
              Set(challenge.keys) == ["instance", "serverNonce", "proof"],
              let instance = challenge["instance"], let serverNonce = challenge["serverNonce"],
              instance.range(of: "\\A[A-Za-z0-9_-]{43}\\z", options: .regularExpression) != nil,
              serverNonce.range(of: "\\A[A-Za-z0-9_-]{43}\\z", options: .regularExpression) != nil,
              let serverProof = decodeHex(challenge["proof"] ?? "") else { throw Failure.unavailable }
        let message = ["nagi-server-v2", origin, instance, client, serverNonce, method, path, bodyHash].joined(separator: "\n")
        guard HMAC<SHA256>.isValidAuthenticationCode(serverProof, authenticating: Data(message.utf8),
                                                     using: SymmetricKey(data: Data(secret.utf8))) else { throw Failure.unavailable }
        let clientProof = hex(mac(secret, "nagi-client-v2", origin, instance, client, serverNonce, method, path, bodyHash))
        return "NagiProof " + [instance, client, serverNonce, clientProof].joined(separator: ".")
    }

    /// One owner-proved request to this computer's reader. POST bodies are JSON.
    public static func request(origin: String, method: String, path: String, body: Data? = nil,
                               directory: String, limit: Int) async throws -> Data {
        guard validOrigin(origin), path.hasPrefix("/"), !path.hasPrefix("//"),
              let url = URL(string: origin + path) else { throw Failure.unavailable }
        let secret = try secret(directory: directory)
        let session = makeSession()
        defer { session.invalidateAndCancel() }
        let authorization = try await authorize(session, secret: secret, origin: origin,
                                                method: method, path: path, body: body ?? Data())
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = 5
        request.setValue(authorization, forHTTPHeaderField: "Authorization")
        if let body {
            request.httpBody = body
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.setValue("1", forHTTPHeaderField: "X-Progress-Desk")
        }
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw Failure.unavailable }
        guard http.statusCode == 200 else { throw Failure.status(http.statusCode) }
        guard data.count <= limit else { throw Failure.unavailable }
        return data
    }

    /// A one-use, ten-second launch ticket URL for the web view. Native code only.
    public static func launch(page: URL, directory: String) async throws -> URL {
        guard SourceLinks.privateURL(page, sameOriginAs: page), page.fragment == nil,
              let port = page.port else { throw Failure.unavailable }
        let origin = "http://127.0.0.1:\(port)"
        let body = try JSONSerialization.data(withJSONObject: ["path": page.path])
        let data = try await request(origin: origin, method: "POST", path: "/auth/launch", body: body,
                                     directory: directory, limit: 4096)
        guard let value = try JSONSerialization.jsonObject(with: data) as? [String: String],
              let raw = value["url"], let url = URL(string: raw), url.scheme == page.scheme,
              url.host == page.host, url.port == page.port, url.path == page.path,
              url.user == nil, url.password == nil, url.query == nil,
              url.fragment?.range(of: "\\Anagi-launch=[A-Za-z0-9_-]{43}\\z", options: .regularExpression) != nil else { throw Failure.unavailable }
        return url
    }
}

private final class NoRedirect: NSObject, URLSessionTaskDelegate {
    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest,
                    completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}
