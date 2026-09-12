/// Formatos de texto compartidos por Inicio (P04), Misiones (P19), Logros
/// (P20) y la bandeja de notificaciones.
///
/// Todo el texto sale en español y con el tono del Reino. Aquí no se calcula
/// nada del juego: solo se da forma legible a números y fechas que el
/// servidor ya resolvió.
library;

const List<String> _meses = <String>[
  'ene',
  'feb',
  'mar',
  'abr',
  'may',
  'jun',
  'jul',
  'ago',
  'sep',
  'oct',
  'nov',
  'dic',
];

const List<String> _mesesLargos = <String>[
  'enero',
  'febrero',
  'marzo',
  'abril',
  'mayo',
  'junio',
  'julio',
  'agosto',
  'septiembre',
  'octubre',
  'noviembre',
  'diciembre',
];

/// Tiempo de estudio en palabras: "3 h 42 min", "42 min", "Menos de 1 min".
String tiempoLegible(int segundos) {
  if (segundos <= 0) return '0 min';
  final int minutosTotales = segundos ~/ 60;
  if (minutosTotales <= 0) return 'Menos de 1 min';
  final int horas = minutosTotales ~/ 60;
  final int minutos = minutosTotales % 60;
  if (horas <= 0) return '$minutos min';
  if (minutos == 0) return '$horas h';
  return '$horas h $minutos min';
}

/// Igual que [tiempoLegible] pero partiendo de minutos.
String minutosLegibles(int minutos) => tiempoLegible(minutos * 60);

/// Cuenta atrás del reinicio de misiones: "5 h 12 min" o "12:34".
String cuentaAtras(int segundos) {
  if (segundos <= 0) return 'en un instante';
  final int horas = segundos ~/ 3600;
  if (horas >= 1) {
    final int minutos = (segundos % 3600) ~/ 60;
    return minutos == 0 ? '$horas h' : '$horas h $minutos min';
  }
  final int minutos = segundos ~/ 60;
  final int resto = segundos % 60;
  return '${minutos.toString().padLeft(2, '0')}:'
      '${resto.toString().padLeft(2, '0')}';
}

/// Fecha breve para medallas y notificaciones: "10 sep".
String fechaCorta(DateTime fecha) {
  final String mes = _meses[(fecha.month - 1).clamp(0, 11)];
  return '${fecha.day} $mes';
}

/// Fecha completa para las hojas de detalle: "10 de septiembre de 2026".
String fechaLarga(DateTime fecha) {
  final String mes = _mesesLargos[(fecha.month - 1).clamp(0, 11)];
  return '${fecha.day} de $mes de ${fecha.year}';
}

/// Antigüedad relativa de un mensaje: "ahora", "hace 5 min", "ayer", "10 sep".
String relativo(DateTime momento) {
  final DateTime ahora = DateTime.now();
  final Duration diferencia = ahora.difference(momento);
  if (diferencia.isNegative) return 'programado';
  if (diferencia.inMinutes < 1) return 'ahora';
  if (diferencia.inMinutes < 60) return 'hace ${diferencia.inMinutes} min';
  if (diferencia.inHours < 24) return 'hace ${diferencia.inHours} h';
  if (diferencia.inDays == 1) return 'ayer';
  if (diferencia.inDays < 7) return 'hace ${diferencia.inDays} días';
  return fechaCorta(momento);
}

/// Saludo de la cabecera del Inicio.
///
/// La clave la elige el servidor (`greeting_key`); si llega vacía o
/// desconocida se recurre a la hora local, nunca a un texto técnico.
String saludoDelReino(String clave, String nombre) {
  final String base = switch (clave.trim().toLowerCase()) {
    'morning' || 'good_morning' || 'manana' => 'Buenos días',
    'afternoon' || 'good_afternoon' || 'tarde' => 'Buenas tardes',
    'evening' || 'good_evening' || 'night' || 'late_night' => 'Buenas noches',
    'welcome' || 'first_day' || 'new_hero' => 'Bienvenido al Reino',
    'welcome_back' || 'comeback' || 'reactivation' => 'Qué bueno verte de vuelta',
    'streak_at_risk' || 'at_risk' || 'last_call' => 'Tu racha te espera',
    'goal_met' || 'daily_goal_met' => 'Objetivo del día cumplido',
    'streak_milestone' || 'milestone' => 'Hoy hay hito a la vista',
    _ => _saludoPorHora(DateTime.now().hour),
  };
  return nombre.trim().isEmpty ? base : '$base, ${nombre.trim()}';
}

String _saludoPorHora(int hora) {
  if (hora < 6) return 'Buenas noches';
  if (hora < 13) return 'Buenos días';
  if (hora < 20) return 'Buenas tardes';
  return 'Buenas noches';
}

/// Porcentaje redondeado y con su símbolo, para dominio y progreso.
String porcentaje(double fraccion) => '${(fraccion.clamp(0, 1) * 100).round()} %';
