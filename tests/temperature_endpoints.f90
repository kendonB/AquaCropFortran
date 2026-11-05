program temperature_endpoints
    use ac_kinds, only: sp, int8, int32, intEnum
    use ac_global, only: rep_clim, datatype_daily, datatype_decadely, datatype_monthly, &
        SetTemperatureFile, SetTemperatureFilefull, LoadClim, SetTemperatureRecord, &
        SetSimulParam_GDDMethod, SetPathNameSimul
    use ac_tempprocessing, only: ReadTemperatureFilefull, TemperatureFilefull_exists, &
        GrowingDegreeDays, SumCalendarDays, TemperatureFileCoveringCropPeriod
    implicit none

    type(rep_clim) :: record
    integer :: failures, unit, i, rc
    real(sp) :: low, high

    failures = 0
    call SetSimulParam_GDDMethod(3_int8)
    call SetPathNameSimul('./')

    ! Daily GDD values are 0, 10, 20; the final observation must not wrap to the first.
    call load_temperature(datatype_daily, [5._sp, 15._sp, 25._sp])
    call check_gdd('daily crop ending on last weather day', 3, record%FromDayNr, 30)
    call check_gdd('daily crop starting on last weather day', 1, record%ToDayNr, 20)
    call check_gdd('daily crop extending beyond the record', 4, record%FromDayNr, -9)
    call check_calendar_days('daily threshold reached on final day', 25, record%FromDayNr, 3)
    call check_calendar_days('daily threshold starting on final day', 20, record%ToDayNr, 1)
    call check_calendar_days('daily threshold beyond available GDD', 31, record%FromDayNr, -9)

    call TemperatureFileCoveringCropPeriod(record%FromDayNr+1, record%ToDayNr)
    open(newunit=unit, file='TCrop.SIM', status='old', action='read')
    do i = 1, 2
        read(unit, *, iostat=rc) low, high
        if (rc /= 0) error stop 'Missing TCrop row'
        if (abs(low-(5._sp+10._sp*i)) > 0.0001_sp .or. &
            abs(high-(5._sp+10._sp*i)) > 0.0001_sp) then
            print *, 'Incorrect TCrop row:', i, low, high
            failures = failures + 1
        end if
    end do
    read(unit, *, iostat=rc) low, high
    if (rc >= 0) error stop 'Unexpected extra TCrop row'
    close(unit)

    ! Constant temperatures make interpolated ten-day/monthly daily GDD exactly 10.
    call load_temperature(datatype_decadely, [15._sp, 15._sp, 15._sp, 15._sp])
    call check_gdd('ten-day record final two days', 2, record%ToDayNr-1, 20)
    call check_gdd('ten-day record final day only', 1, record%ToDayNr, 10)
    call check_gdd('ten-day record insufficient coverage', 3, record%ToDayNr-1, -9)
    call check_calendar_days('ten-day threshold reached on final day', 20, record%ToDayNr-1, 2)
    call check_calendar_days('ten-day threshold starting on final day', 10, record%ToDayNr, 1)
    call check_calendar_days('ten-day threshold beyond available GDD', 21, record%ToDayNr-1, -9)
    call load_temperature(datatype_monthly, [15._sp, 15._sp, 15._sp, 15._sp])
    call check_gdd('monthly record final two days', 2, record%ToDayNr-1, 20)
    call check_gdd('monthly record final day only', 1, record%ToDayNr, 10)
    call check_gdd('monthly record insufficient coverage', 3, record%ToDayNr-1, -9)
    call check_calendar_days('monthly threshold reached on final day', 20, record%ToDayNr-1, 2)
    call check_calendar_days('monthly threshold starting on final day', 10, record%ToDayNr, 1)
    call check_calendar_days('monthly threshold beyond available GDD', 21, record%ToDayNr-1, -9)

    if (failures /= 0) error stop 'Temperature endpoint tests failed'
    print *, 'Temperature endpoint tests passed'

contains

    subroutine load_temperature(datatype, values)
        integer(intEnum), intent(in) :: datatype
        real(sp), intent(in) :: values(:)
        integer :: file, j
        character(len=1024) :: description

        open(newunit=file, file='endpoint.Tnx', status='replace', action='write')
        write(file, '(a)') 'Temperature endpoint regression'
        write(file, *) datatype + 1 ! File codes are 1=daily, 2=ten-day, 3=monthly.
        write(file, *) 1
        write(file, *) 1
        write(file, *) 2016
        write(file, '(a)') '', 'Tmin Tmax', '========='
        do j = 1, size(values)
            write(file, *) values(j), values(j)
        end do
        close(file)
        call SetTemperatureFile('endpoint.Tnx')
        call SetTemperatureFilefull('endpoint.Tnx')
        call LoadClim('endpoint.Tnx', description, record)
        call SetTemperatureRecord(record)
        call ReadTemperatureFilefull()
        TemperatureFilefull_exists = .true.
    end subroutine load_temperature

    subroutine check_gdd(label, days, first_day, expected)
        character(len=*), intent(in) :: label
        integer(int32), intent(in) :: days, first_day, expected
        integer(int32) :: actual

        actual = GrowingDegreeDays(days, first_day, 5._sp, 30._sp, 0._sp, 0._sp, .false.)
        if (actual /= expected) then
            print *, label, ': expected ', expected, ', got ', actual
            failures = failures + 1
        end if
    end subroutine check_gdd
    subroutine check_calendar_days(label, gdd, first_day, expected)
        character(len=*), intent(in) :: label
        integer(int32), intent(in) :: gdd, first_day, expected
        integer(int32) :: actual

        actual = SumCalendarDays(gdd, first_day, 5._sp, 30._sp, 0._sp, 0._sp)
        if (actual /= expected) then
            print *, label, ': expected ', expected, ', got ', actual
            failures = failures + 1
        end if
    end subroutine check_calendar_days
end program temperature_endpoints
