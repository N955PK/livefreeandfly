import CoreLocation
import Foundation

/// Phone position for placing the box from the judges' spot when the Hub isn't talking. CoreLocation rather
/// than the web view's geolocation: one permission prompt, no secure-origin rules for the acro:// scheme, and
/// fixes keep flowing while the panel is open.
final class LocationProvider: NSObject, CLLocationManagerDelegate {
    private let manager = CLLocationManager()
    private var onFix: ((Double, Double, Double) -> Void)?
    private var onError: ((String) -> Void)?

    func start(onFix: @escaping (Double, Double, Double) -> Void, onError: @escaping (String) -> Void) {
        self.onFix = onFix
        self.onError = onError
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyBest
        manager.distanceFilter = 3
        switch manager.authorizationStatus {
        case .notDetermined: manager.requestWhenInUseAuthorization()
        case .denied, .restricted: onError(Self.deniedMessage)
        default: manager.startUpdatingLocation()
        }
    }

    private static let deniedMessage = "allow Location for WingRock in Settings"

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        switch manager.authorizationStatus {
        case .authorizedWhenInUse, .authorizedAlways: manager.startUpdatingLocation()
        case .denied, .restricted: onError?(Self.deniedMessage)
        default: break
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let loc = locations.last, loc.horizontalAccuracy >= 0 else { return }
        onFix?(loc.coordinate.latitude, loc.coordinate.longitude, loc.horizontalAccuracy)
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        onError?(error.localizedDescription)
    }
}
