"use client";

import { useQuery } from "@tanstack/react-query";

import { queries } from "@/lib/api/queries";

/** Tra tên hiển thị từ danh mục xe (`GET /api/v1/vehicles`); fallback về mã xe nếu chưa có. */
export function useVehicleName(vehicleModel: string): string {
  const vehicles = useQuery({ ...queries.vehicles(), staleTime: 5 * 60_000 });
  return vehicles.data?.find((v) => v.vehicle_model === vehicleModel)?.display_name ?? vehicleModel;
}
