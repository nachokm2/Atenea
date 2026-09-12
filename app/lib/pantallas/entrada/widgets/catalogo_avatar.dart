/// Catálogo de rasgos del avatar para la creación de personaje (P03).
///
/// El avatar del MVP es un muñeco 2D por capas (§6.4 del documento de UX). El
/// manifiesto de capas con sus recursos gráficos lo sirve el Reino en
/// `GET /avatar`, pero durante la creación todavía no hay personaje: la vista
/// previa se pinta aquí con las **mismas claves** que viajan a la API
/// (`skin_tone`, `face_id`, `ear_style`, `hair_style_id`, `hair_color`), para
/// que lo que el usuario elige y lo que el servidor guarda sean lo mismo.
///
/// Los colores de este archivo son **contenido del catálogo de assets** (piel,
/// cabello y atuendo de cada Orden), no tokens de interfaz: equivalen a los
/// PNG por capa que aún no existen. Todo el resto de la pantalla usa
/// exclusivamente la paleta semántica del tema.
library;

import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../../datos/repositorios.dart';

/// Una opción elegible del catálogo: su clave de API y su nombre visible.
@immutable
class OpcionAvatar {
  const OpcionAvatar({
    required this.clave,
    required this.etiqueta,
    this.color,
  });

  /// Clave literal que viaja a la API (`skin_03`, `hair_01`, `pointed`…).
  final String clave;

  /// Nombre visible en español.
  final String etiqueta;

  /// Color de muestra, cuando la opción es un color (piel o cabello).
  final Color? color;
}

/// Identidad visual de una Orden: colores del atuendo, emblema y lema.
@immutable
class OrdenVisual {
  const OrdenVisual({
    required this.principal,
    required this.acento,
    required this.metal,
    required this.emblema,
    required this.lema,
    required this.descripcion,
    required this.disponible,
  });

  /// Color del atuendo.
  final Color principal;

  /// Color de los ribetes y del emblema.
  final Color acento;

  /// Color de hombreras, hebilla y herrajes.
  final Color metal;

  /// Icono del emblema del pecho y de la tarjeta.
  final IconData emblema;

  /// Lema corto de la Orden.
  final String lema;

  /// Una línea sobre el estilo, nunca sobre la capacidad de aprender.
  final String descripcion;

  /// ¿Se puede elegir ya? Las Órdenes de fase 2 se muestran en silueta.
  final bool disponible;
}

/// Todas las opciones gratuitas del avatar del MVP.
abstract final class CatalogoAvatar {
  /// Seis tonos de piel (`avatar_configs.skin_tone`).
  static const List<OpcionAvatar> tonosPiel = <OpcionAvatar>[
    OpcionAvatar(clave: 'skin_01', etiqueta: 'Marfil', color: Color(0xFFF3D6BE)),
    OpcionAvatar(clave: 'skin_02', etiqueta: 'Arena', color: Color(0xFFE4B893)),
    OpcionAvatar(clave: 'skin_03', etiqueta: 'Miel', color: Color(0xFFC98C63)),
    OpcionAvatar(clave: 'skin_04', etiqueta: 'Ámbar', color: Color(0xFFA96C44)),
    OpcionAvatar(clave: 'skin_05', etiqueta: 'Caoba', color: Color(0xFF7B4A2B)),
    OpcionAvatar(clave: 'skin_06', etiqueta: 'Ébano', color: Color(0xFF4E2E1C)),
  ];

  /// Cuatro rostros (`avatar_configs.face_id`).
  static const List<OpcionAvatar> rostros = <OpcionAvatar>[
    OpcionAvatar(clave: 'face_01', etiqueta: 'Serena'),
    OpcionAvatar(clave: 'face_02', etiqueta: 'Decidida'),
    OpcionAvatar(clave: 'face_03', etiqueta: 'Amable'),
    OpcionAvatar(clave: 'face_04', etiqueta: 'Intensa'),
  ];

  /// Dos formas de oreja (`avatar_configs.ear_style`).
  static const List<OpcionAvatar> orejas = <OpcionAvatar>[
    OpcionAvatar(clave: 'round', etiqueta: 'Redondeadas'),
    OpcionAvatar(clave: 'pointed', etiqueta: 'Élficas'),
  ];

  /// Ocho estilos de cabello (`avatar_configs.hair_style_id`).
  static const List<OpcionAvatar> cabellos = <OpcionAvatar>[
    OpcionAvatar(clave: 'hair_01', etiqueta: 'Corta'),
    OpcionAvatar(clave: 'hair_02', etiqueta: 'Ondulada'),
    OpcionAvatar(clave: 'hair_03', etiqueta: 'Larga'),
    OpcionAvatar(clave: 'hair_04', etiqueta: 'Coleta'),
    OpcionAvatar(clave: 'hair_05', etiqueta: 'Rizada'),
    OpcionAvatar(clave: 'hair_06', etiqueta: 'Moño'),
    OpcionAvatar(clave: 'hair_07', etiqueta: 'Trenzas'),
    OpcionAvatar(clave: 'hair_08', etiqueta: 'Rapada'),
  ];

  /// Diez colores de cabello (`avatar_configs.hair_color`).
  static const List<OpcionAvatar> coloresCabello = <OpcionAvatar>[
    OpcionAvatar(clave: 'hair_black', etiqueta: 'Negro', color: Color(0xFF221C22)),
    OpcionAvatar(clave: 'hair_brown', etiqueta: 'Castaño', color: Color(0xFF4A2F21)),
    OpcionAvatar(clave: 'hair_light_brown', etiqueta: 'Avellana', color: Color(0xFF8A5A34)),
    OpcionAvatar(clave: 'hair_blonde', etiqueta: 'Trigo', color: Color(0xFFD9A94E)),
    OpcionAvatar(clave: 'hair_red', etiqueta: 'Cobre', color: Color(0xFFA8391F)),
    OpcionAvatar(clave: 'hair_silver', etiqueta: 'Plata', color: Color(0xFFD6DCE6)),
    OpcionAvatar(clave: 'hair_ash', etiqueta: 'Ceniza', color: Color(0xFF8A8F9C)),
    OpcionAvatar(clave: 'hair_blue', etiqueta: 'Azul arcano', color: Color(0xFF3E6FD1)),
    OpcionAvatar(clave: 'hair_green', etiqueta: 'Verde bosque', color: Color(0xFF2F7A55)),
    OpcionAvatar(clave: 'hair_violet', etiqueta: 'Violeta', color: Color(0xFF8B5BD6)),
  ];

  /// Siluetas ofrecidas (`avatar_configs.body_type`).
  static const List<TipoCuerpo> siluetas = TipoCuerpo.values;

  /// Color de un tono de piel; si la clave no existe, el primero.
  static Color piel(String clave) => _buscar(tonosPiel, clave).color!;

  /// Color de un cabello; si la clave no existe, el primero.
  static Color cabello(String clave) => _buscar(coloresCabello, clave).color!;

  /// Índice del rostro (0–3) a partir de su clave.
  static int indiceRostro(String clave) {
    final int i = rostros.indexWhere((OpcionAvatar o) => o.clave == clave);
    return i < 0 ? 0 : i;
  }

  /// Índice del estilo de cabello (0–7) a partir de su clave.
  static int indiceCabello(String clave) {
    final int i = cabellos.indexWhere((OpcionAvatar o) => o.clave == clave);
    return i < 0 ? 0 : i;
  }

  /// Identidad visual de cada Orden.
  static OrdenVisual orden(Arquetipo arquetipo) => switch (arquetipo) {
        Arquetipo.acero => const OrdenVisual(
            principal: Color(0xFF6B7A8F),
            acento: Color(0xFFB23A35),
            metal: Color(0xFFC9D2DE),
            emblema: Icons.shield_rounded,
            lema: 'Disciplina y filo',
            descripcion: 'Avanzas de frente, con un golpe firme cada día.',
            disponible: true,
          ),
        Arquetipo.arcano => const OrdenVisual(
            principal: Color(0xFF4B3A8C),
            acento: Color(0xFFF2B84B),
            metal: Color(0xFFC8B6F5),
            emblema: Icons.auto_awesome_rounded,
            lema: 'El saber es luz',
            descripcion: 'Te fascina entender por qué funcionan las cosas.',
            disponible: true,
          ),
        Arquetipo.bosque => const OrdenVisual(
            principal: Color(0xFF2F6B47),
            acento: Color(0xFF8A5A34),
            metal: Color(0xFFBFD9C4),
            emblema: Icons.forest_rounded,
            lema: 'Paciencia y puntería',
            descripcion: 'Observas, apuntas y aciertas sin hacer ruido.',
            disponible: true,
          ),
        Arquetipo.muro => const OrdenVisual(
            principal: Color(0xFF3B4A63),
            acento: Color(0xFF4DA3FF),
            metal: Color(0xFFAEBBD0),
            emblema: Icons.castle_rounded,
            lema: 'Nada pasa sin ser visto',
            descripcion: 'Resistes: tu fuerza está en volver siempre.',
            disponible: true,
          ),
        Arquetipo.estandarte => const OrdenVisual(
            principal: Color(0xFF8A3B5E),
            acento: Color(0xFFF2B84B),
            metal: Color(0xFFE0C3D2),
            emblema: Icons.flag_rounded,
            lema: 'Nadie avanza solo',
            descripcion: 'Abrirá sus puertas en una próxima temporada.',
            disponible: false,
          ),
        Arquetipo.corona => const OrdenVisual(
            principal: Color(0xFF7A5B1F),
            acento: Color(0xFFF5E0A3),
            metal: Color(0xFFE8D089),
            emblema: Icons.workspace_premium_rounded,
            lema: 'La palabra justa',
            descripcion: 'Abrirá sus puertas en una próxima temporada.',
            disponible: false,
          ),
        Arquetipo.runas => const OrdenVisual(
            principal: Color(0xFF2E5F6B),
            acento: Color(0xFF7FE3E8),
            metal: Color(0xFFA9D8DE),
            emblema: Icons.hexagon_rounded,
            lema: 'Todo deja huella',
            descripcion: 'Abrirá sus puertas en una próxima temporada.',
            disponible: false,
          ),
        Arquetipo.bosqueAntiguo => const OrdenVisual(
            principal: Color(0xFF3D5B32),
            acento: Color(0xFFA8C66C),
            metal: Color(0xFFCBDDB4),
            emblema: Icons.park_rounded,
            lema: 'Las raíces recuerdan',
            descripcion: 'Abrirá sus puertas en una próxima temporada.',
            disponible: false,
          ),
      };

  /// Órdenes que se pueden elegir hoy (las cuatro del MVP).
  static List<Arquetipo> get ordenesDisponibles => Arquetipo.delMvp;

  /// Órdenes anunciadas pero todavía cerradas (fase 2).
  static List<Arquetipo> get ordenesFuturas => Arquetipo.values
      .where((Arquetipo a) => !Arquetipo.delMvp.contains(a))
      .toList(growable: false);

  /// Rasgos al azar para el botón "Aleatorio".
  ///
  /// La forma de tratamiento no se sortea: es identidad, no adorno.
  static RasgosAvatar rasgosAlAzar(math.Random azar, RasgosAvatar previos) {
    return RasgosAvatar(
      tipoCuerpo: siluetas[azar.nextInt(siluetas.length)],
      tonoPiel: tonosPiel[azar.nextInt(tonosPiel.length)].clave,
      rostro: rostros[azar.nextInt(rostros.length)].clave,
      orejas: orejas[azar.nextInt(orejas.length)].clave,
      cabello: cabellos[azar.nextInt(cabellos.length)].clave,
      colorCabello: coloresCabello[azar.nextInt(coloresCabello.length)].clave,
      formaTrato: previos.formaTrato,
      colorAcento: previos.colorAcento,
      versionAssets: previos.versionAssets,
    );
  }

  static OpcionAvatar _buscar(List<OpcionAvatar> donde, String clave) {
    for (final OpcionAvatar o in donde) {
      if (o.clave == clave) return o;
    }
    return donde.first;
  }
}
