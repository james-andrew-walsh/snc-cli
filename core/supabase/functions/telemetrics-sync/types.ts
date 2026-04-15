export interface OEMTelematicsProvider {
  providerKey: string;
  sync(config: Record<string, unknown>): Promise<TelematicsSnapshotInsert[]>;
}

export interface TelematicsSnapshotInsert {
  equipmentCode: string;
  equipmentHcssId?: string;
  latitude?: number;
  longitude?: number;
  locationDateTime?: string;
  isLocationStale: boolean;
  hourMeterReadingInHours?: number;
  hourMeterReadingDateTime?: string;
  hourMeterReadingSource?: string;
  engineStatus?: string; // "ON" | "OFF" | "IDLE" | "UNKNOWN"
  engineStatusDateTime?: string;
  engineStatusAt?: string;
  idleHours?: number; // OEM-only field; null for E360
  productiveHours?: number; // OEM-only field; null for E360
  fuelRemainingPercent?: number; // JDLink / ISO 15143-3
  fuelConsumedLitres?: number; // JDLink / ISO 15143-3
  defRemainingPercent?: number; // JDLink / ISO 15143-3
  providerKey: string;
  snapshotAt: string;
}
